"""Retrieval for the "Find the right product" workspace — the 201 half.

Three modes over the same collection, the same structured filters, and the same
stored product text:

    keyword   Atlas Search (`$search`) — BM25 over sku/name/summary/description
              /tags, so an exact SKU read off a product card matches.
    semantic  Atlas Vector Search (`$vectorSearch`) over the stored embedding.
    hybrid    Server-side `$rankFusion` when the cluster supports it, otherwise a
              deterministic reciprocal-rank-fusion fallback computed in-process.

Every function returns the exact aggregation it ran plus the retrieval metadata
the UI needs, so the explanation shown next to a result is built only from
stored fields and real scores — never from invented reasoning.
"""

from pymongo.errors import OperationFailure

from lib.atlas_client import TYPE_ATTRIBUTE, products
from lib.catalog import LIST_PROJECTION, build_filter
from lib.embeddings import embedding_dim, get_embedder, provider_name

TEXT_INDEX = "pcs_products_text_index"
VECTOR_INDEX = "pcs_products_vector_index"

KEYWORD_PATHS = ["sku", "name", "summary", "description", "tags"]
RRF_K = 60  # the standard reciprocal-rank-fusion constant

MODES = ["keyword", "semantic", "hybrid"]

# Paths the structured filters use. Declared as `token`/`number` in the Atlas
# Search index and as `filter` in the vector index, so the same UI selections
# can pre-filter every retrieval mode.
FILTER_PATHS = ["product_type", "category", "status", "price.amount",
                *(path for path, _label, _opts in TYPE_ATTRIBUTE.values())]

# Substrings Atlas uses when a search/vector index is absent or still building.
_MISSING_INDEX_MARKERS = ("index not found", "no such index", "$vectorSearch",
                          "Search index", "PlanExecutor error")


def text_index_definition() -> dict:
    """Atlas Search index: BM25 on the text fields, tokens for the filters.

    The mapping is explicit rather than dynamic so the searchable surface and
    the filterable surface are both readable in one place.
    """
    fields: dict = {p: {"type": "string"} for p in KEYWORD_PATHS}
    for path in FILTER_PATHS:
        kind = "number" if path.endswith("amount") else "token"
        if "." in path:
            parent, child = path.split(".")
            fields.setdefault(parent, {"type": "document", "fields": {}})
            fields[parent]["fields"][child] = {"type": kind}
        else:
            fields[path] = {"type": kind}
    return {"name": TEXT_INDEX, "type": "search",
            "definition": {"mappings": {"dynamic": False, "fields": fields}}}


def vector_index_definition(dim: int | None = None) -> dict:
    """Vector Search index: cosine over `embedding`, plus the filter paths."""
    return {
        "name": VECTOR_INDEX, "type": "vectorSearch",
        "definition": {"fields": [
            {"type": "vector", "path": "embedding",
             "numDimensions": dim or embedding_dim(), "similarity": "cosine"},
            *({"type": "filter", "path": p} for p in FILTER_PATHS),
        ]},
    }


def _token_filters(filters: dict | None) -> list[dict]:
    """Structured filters expressed as Atlas Search `compound.filter` clauses."""
    f = filters or {}
    clauses: list[dict] = []
    for path in ("product_type", "category", "status"):
        if f.get(path):
            clauses.append({"equals": {"path": path, "value": f[path]}})
    price: dict = {"path": "price.amount"}
    if f.get("price_min") is not None:
        price["gte"] = float(f["price_min"])
    if f.get("price_max") is not None:
        price["lte"] = float(f["price_max"])
    if len(price) > 1:
        clauses.append({"range": price})
    if f.get("type_attribute") and f.get("product_type") in TYPE_ATTRIBUTE:
        path = TYPE_ATTRIBUTE[f["product_type"]][0]
        clauses.append({"equals": {"path": path, "value": f["type_attribute"]}})
    return clauses


def keyword_stage(query: str, filters: dict | None) -> dict:
    return {
        "$search": {
            "index": TEXT_INDEX,
            "compound": {
                "must": [{"text": {"query": query, "path": KEYWORD_PATHS}}],
                "filter": _token_filters(filters),
            },
        }
    }


def vector_stage(query_vector: list[float], filters: dict | None,
                 limit: int) -> dict:
    stage = {
        "index": VECTOR_INDEX,
        "path": "embedding",
        "queryVector": query_vector,
        "numCandidates": max(limit * 15, 100),
        "limit": limit,
    }
    # $vectorSearch pre-filters on fields declared as `filter` in the index.
    flt = build_filter(filters)
    if flt:
        stage["filter"] = flt
    return {"$vectorSearch": stage}


def keyword_pipeline(query: str, filters: dict | None, limit: int) -> list[dict]:
    return [
        keyword_stage(query, filters),
        {"$limit": limit},
        {"$addFields": {"keyword_score": {"$meta": "searchScore"}}},
        {"$project": LIST_PROJECTION},
    ]


def semantic_pipeline(query: str, filters: dict | None,
                      limit: int) -> list[dict]:
    query_vector = get_embedder().embed_query(query)
    return [
        vector_stage(query_vector, filters, limit),
        {"$addFields": {"vector_score": {"$meta": "vectorSearchScore"}}},
        {"$project": LIST_PROJECTION},
    ]


def rank_fusion_pipeline(query: str, filters: dict | None,
                         limit: int) -> list[dict]:
    """Server-side rank fusion: Atlas ranks each leg, then fuses the ranks."""
    query_vector = get_embedder().embed_query(query)
    return [
        {"$rankFusion": {
            "input": {"pipelines": {
                "keyword": [keyword_stage(query, filters), {"$limit": limit}],
                "semantic": [vector_stage(query_vector, filters, limit)],
            }},
            "combination": {"weights": {"keyword": 1.0, "semantic": 1.0}},
            "scoreDetails": True,
        }},
        {"$limit": limit},
        {"$addFields": {"fused_score": {"$meta": "score"},
                        "score_details": {"$meta": "scoreDetails"}}},
        {"$project": LIST_PROJECTION},
    ]


def _run(pipeline: list[dict]) -> list[dict]:
    rows = list(products().aggregate(pipeline))
    for r in rows:
        r["_id"] = str(r["_id"])
    return rows


def _index_hint(error: Exception) -> str:
    text = str(error)
    if any(m.lower() in text.lower() for m in _MISSING_INDEX_MARKERS):
        return ("The Atlas Search / Vector Search index this mode needs is not "
                "queryable yet. Run `python3 scripts/create_indexes.py` and "
                "allow 1–2 minutes for Atlas to finish building it "
                "(`python3 scripts/status.py` shows the state).")
    return "Atlas rejected the query. The exact server message is shown below."


# ── Deterministic fallback fusion ──────────────────────────────────────────

def rrf_fuse(keyword: list[dict], semantic: list[dict],
             limit: int) -> list[dict]:
    """Reciprocal-rank fusion over two ranked lists: score = Σ 1/(k + rank).

    Deterministic and computed in-process, so hybrid still works on clusters
    without server-side `$rankFusion`. Each result keeps the rank it held in
    each leg, which is what the UI reports.
    """
    merged: dict[str, dict] = {}
    scores: dict[str, float] = {}
    for leg_name, rows in (("keyword", keyword), ("semantic", semantic)):
        for rank, doc in enumerate(rows, start=1):
            key = doc["product_id"]
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
            entry = merged.setdefault(key, dict(doc))
            entry[f"{leg_name}_rank"] = rank
            for field in ("keyword_score", "vector_score"):
                if doc.get(field) is not None:
                    entry[field] = doc[field]
    ordered = sorted(scores, key=lambda k: (-scores[k], k))[:limit]
    return [merged[k] | {"fused_score": round(scores[k], 6)} for k in ordered]


# ── Truthful, metadata-only explanations ───────────────────────────────────

def explain_result(doc: dict, mode: str, fusion: str | None = None) -> str:
    """Explain a hit using only stored fields and real retrieval metadata."""
    price = (doc.get("price") or {}).get("amount")
    facts = [f"stored `status: {doc.get('status')}`",
             f"`category: {doc.get('category')}`"]
    if price is not None:
        facts.append(f"`price.amount: {price:,.2f}`")

    if mode == "keyword":
        score = doc.get("keyword_score")
        lead = (f"Atlas Search matched the query terms in "
                f"{', '.join('`' + p + '`' for p in KEYWORD_PATHS)}"
                + (f" · BM25 score {score:.3f}" if score is not None else ""))
    elif mode == "semantic":
        score = doc.get("vector_score")
        lead = ("Atlas Vector Search matched the stored embedding of this "
                f"product's text (provider `{provider_name()}`, "
                f"{embedding_dim()} dims)"
                + (f" · cosine similarity {score:.4f}" if score is not None
                   else ""))
    else:
        parts = []
        if doc.get("keyword_rank"):
            parts.append(f"keyword rank #{doc['keyword_rank']}")
        if doc.get("semantic_rank"):
            parts.append(f"semantic rank #{doc['semantic_rank']}")
        detail = " and ".join(parts) if parts else "both retrieval legs"
        score = doc.get("fused_score")
        lead = (f"Fused by {fusion or 'rank fusion'} from {detail}"
                + (f" · fused score {score:.6f}" if score is not None else ""))
    return f"{lead}. Shown fields come from the document: {', '.join(facts)}."


# ── Unified entry point used by the search workspace ───────────────────────

def run_search(query: str, filters: dict | None = None, *,
               mode: str = "hybrid", limit: int = 6) -> dict:
    """Run one retrieval mode and return results plus honest run metadata."""
    if mode not in MODES:
        raise ValueError(f"Unknown mode '{mode}'. Use one of {MODES}.")

    out = {"mode": mode, "results": [], "pipeline": [], "fusion": None,
           "legs": {}, "filters": build_filter(filters), "error": None,
           "notes": []}
    try:
        if mode == "keyword":
            out["pipeline"] = keyword_pipeline(query, filters, limit)
            out["results"] = _run(out["pipeline"])
            out["legs"] = {"keyword": len(out["results"])}
        elif mode == "semantic":
            out["pipeline"] = semantic_pipeline(query, filters, limit)
            out["results"] = _run(out["pipeline"])
            out["legs"] = {"semantic": len(out["results"])}
        else:
            out.update(_run_hybrid(query, filters, limit))
    except OperationFailure as e:
        out["error"] = {"message": str(e), "hint": _index_hint(e)}
        return out
    except Exception as e:  # noqa: BLE001 — surface the real cause to presenter
        out["error"] = {"message": str(e),
                        "hint": "Check .env configuration for this mode."}
        return out

    for doc in out["results"]:
        doc["explanation"] = explain_result(doc, mode, out["fusion"])
    return out


def _run_hybrid(query: str, filters: dict | None, limit: int) -> dict:
    """Prefer server-side `$rankFusion`; fall back to in-process RRF."""
    pipeline = rank_fusion_pipeline(query, filters, limit)
    try:
        results = _run(pipeline)
        for doc in results:
            details = doc.get("score_details") or {}
            for leg in details.get("details", []):
                name = leg.get("inputPipelineName")
                if name in ("keyword", "semantic"):
                    doc[f"{name}_rank"] = leg.get("inputPipelineRank")
        return {"results": results, "pipeline": pipeline,
                "fusion": "server-side `$rankFusion`",
                "legs": {"keyword": None, "semantic": None},
                "notes": ["Atlas ranked both legs and fused them server-side "
                          "in a single aggregation."]}
    except OperationFailure as e:
        if any(m.lower() in str(e).lower() for m in _MISSING_INDEX_MARKERS) \
                and "rankfusion" not in str(e).lower():
            raise
        keyword = _run(keyword_pipeline(query, filters, limit))
        semantic = _run(semantic_pipeline(query, filters, limit))
        fused = rrf_fuse(keyword, semantic, limit)
        return {"results": fused,
                "pipeline": [keyword_pipeline(query, filters, limit),
                             semantic_pipeline(query, filters, limit)],
                "fusion": f"in-process reciprocal rank fusion (k={RRF_K})",
                "legs": {"keyword": len(keyword), "semantic": len(semantic)},
                "notes": ["This cluster did not accept `$rankFusion`, so both "
                          "legs ran separately and were fused deterministically "
                          "in the app. Server message: " + str(e).split("\n")[0]]}


# ── Optional Voyage AI reranking of the retrieved candidates ───────────────

def rerank_available() -> bool:
    import os

    return bool(os.getenv("VOYAGE_API_KEY"))


def rerank(query: str, results: list[dict]) -> list[dict]:
    """Re-score retrieved candidates with a Voyage AI cross-encoder.

    Runs client-side and only when `VOYAGE_API_KEY` is set. Each result keeps
    its original retrieval rank so the movement is visible and truthful.
    """
    import os

    import voyageai
    from lib.embeddings import product_text

    client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
    model = os.getenv("VOYAGE_RERANK_MODEL", "voyage-rerank-2")
    scored = client.rerank(query=query,
                           documents=[product_text(d) for d in results],
                           model=model, top_k=len(results))
    out = []
    for new_rank, item in enumerate(scored.results, start=1):
        doc = dict(results[item.index])
        doc["retrieval_rank"] = item.index + 1
        doc["rerank_rank"] = new_rank
        doc["rerank_score"] = item.relevance_score
        doc["explanation"] = (
            f"Reranked to #{new_rank} from retrieval #{item.index + 1} by "
            f"`{model}` (relevance {item.relevance_score:.4f}). "
            + doc.get("explanation", ""))
        out.append(doc)
    return out
