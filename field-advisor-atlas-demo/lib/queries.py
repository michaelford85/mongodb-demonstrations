"""Read/write helpers for the Field Advisor demo.

Two families of functions:

* Operational — plain document reads and writes against growers, fields,
  support_cases, and interaction_history (the system-of-record side).
* Advisory retrieval — a hybrid flow that combines Atlas Vector Search over
  the knowledge base with an optional Atlas Search keyword pass, all narrowed
  by the same structured filters used on the operational data.

Everything returns plain Python structures so the Streamlit layer stays thin
and each pipeline is easy to read out loud during a live demo.
"""

from datetime import datetime, timezone

from pymongo.database import Database

from lib.atlas_client import KNOWLEDGE_COLLECTION
from lib.embeddings import get_embedder

VECTOR_INDEX = "knowledge_vector_index"
TEXT_INDEX = "knowledge_text_index"

# Structured-filter keys shared by the operational and semantic sides.
FILTER_FIELDS = ["crop", "region", "season", "product_line", "severity"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_filter(filters: dict | None) -> dict:
    """Turn UI filter selections into an equality-match query fragment."""
    query: dict = {}
    for key in FILTER_FIELDS:
        val = (filters or {}).get(key)
        if val:
            query[key] = val
    return query


# ── Advisory retrieval (semantic + keyword over knowledge_articles) ─────────

def vector_search_articles(db: Database, query_text: str,
                           filters: dict | None = None,
                           limit: int = 6) -> list[dict]:
    """Semantic retrieval via Atlas Vector Search, narrowed by filters."""
    embedder = get_embedder()
    query_vector = embedder.embed_query(query_text)
    stage = {
        "index": VECTOR_INDEX,
        "path": "embedding",
        "queryVector": query_vector,
        "numCandidates": max(limit * 15, 60),
        "limit": limit,
    }
    flt = build_filter(filters)
    if flt:
        stage["filter"] = flt
    pipeline = [
        {"$vectorSearch": stage},
        {"$addFields": {"vector_score": {"$meta": "vectorSearchScore"}}},
        {"$project": {"embedding": 0}},
    ]
    results = list(db[KNOWLEDGE_COLLECTION].aggregate(pipeline))
    for r in results:
        r["_id"] = str(r["_id"])
        r["source"] = "vector"
    return results


def keyword_search_articles(db: Database, query_text: str,
                            filters: dict | None = None,
                            limit: int = 6) -> list[dict]:
    """Keyword retrieval via Atlas Search. Returns [] if the index is absent."""
    must = [{
        "text": {"query": query_text,
                 "path": ["title", "summary", "body", "tags"]},
    }]
    filter_clauses = [{"text": {"query": v, "path": k}}
                      for k, v in build_filter(filters).items()]
    pipeline = [
        {"$search": {"index": TEXT_INDEX,
                     "compound": {"must": must, "filter": filter_clauses}}},
        {"$limit": limit},
        {"$addFields": {"text_score": {"$meta": "searchScore"}}},
        {"$project": {"embedding": 0}},
    ]
    try:
        results = list(db[KNOWLEDGE_COLLECTION].aggregate(pipeline))
    except Exception:
        return []
    for r in results:
        r["_id"] = str(r["_id"])
        r["source"] = "keyword"
    return results


def hybrid_advisory(db: Database, query_text: str, filters: dict | None = None,
                    limit: int = 6) -> dict:
    """Fuse vector + keyword results with reciprocal rank fusion (RRF).

    Returns the ranked articles plus a small debug block the UI uses to show
    exactly which Atlas stages ran — that transparency is part of the story.
    """
    vector = vector_search_articles(db, query_text, filters, limit)
    keyword = keyword_search_articles(db, query_text, filters, limit)

    scores: dict[str, float] = {}
    merged: dict[str, dict] = {}
    for ranked in (vector, keyword):
        for rank, doc in enumerate(ranked):
            key = doc["article_id"]
            scores[key] = scores.get(key, 0.0) + 1.0 / (60 + rank)
            if key not in merged:
                merged[key] = doc
            else:
                merged[key].setdefault("source", "hybrid")
                merged[key]["source"] = "hybrid"

    ranked_ids = sorted(scores, key=lambda k: scores[k], reverse=True)[:limit]
    articles = [merged[k] | {"fused_score": round(scores[k], 6)}
                for k in ranked_ids]
    return {
        "articles": articles,
        "debug": {
            "vector_index": VECTOR_INDEX,
            "vector_hits": len(vector),
            "keyword_index": TEXT_INDEX,
            "keyword_hits": len(keyword),
            "fusion": "reciprocal rank fusion (k=60)",
            "filters_applied": build_filter(filters),
        },
    }


# ── Operational reads (system-of-record documents) ─────────────────────────

def matching_cases(db: Database, filters: dict | None = None,
                   limit: int = 25) -> list[dict]:
    """Structured filter over support_cases — the operational half of search."""
    query = build_filter(filters)
    return list(db.support_cases.find(query, {"interactions": 0})
                .sort("updated_at", -1).limit(limit))


def list_growers(db: Database, limit: int = 200) -> list[dict]:
    return list(db.growers.find().sort("grower_id", 1).limit(limit))


def grower_overview(db: Database, grower_id: str) -> dict:
    """Everything the operational-context screen needs in one call."""
    grower = db.growers.find_one({"grower_id": grower_id})
    fields = list(db.fields.find({"grower_id": grower_id}).sort("crop", 1))
    cases = list(db.support_cases.find({"grower_id": grower_id})
                 .sort("updated_at", -1))
    open_cases = [c for c in cases if c.get("status") != "resolved"]
    # Product history = the distinct product lines seen across this grower's cases.
    product_lines = sorted({c.get("product_line") for c in cases
                            if c.get("product_line")})
    interactions = list(db.interaction_history.find({"grower_id": grower_id})
                        .sort("created_at", -1).limit(10))
    return {
        "grower": grower, "fields": fields, "cases": cases,
        "open_cases": open_cases, "product_lines": product_lines,
        "interactions": interactions,
    }


def get_case(db: Database, case_id: str) -> dict | None:
    return db.support_cases.find_one({"case_id": case_id})


# ── Operational write-back (same app writes to Atlas) ──────────────────────

def add_interaction(db: Database, case_id: str, grower_id: str, *,
                    kind: str, text: str, author: str = "Advisor",
                    new_status: str | None = None) -> dict:
    """Append an interaction to a case and record it in interaction_history.

    Demonstrates that the same application that reads operational data and runs
    vector search also *writes back* to Atlas — a note, recommendation, or
    follow-up status update, in one round trip.
    """
    now = _now()
    interaction = {
        "interaction_id": "INT-" + now.strftime("%Y%m%d%H%M%S%f"),
        "type": kind, "author": author, "text": text, "created_at": now,
    }
    update: dict = {
        "$push": {"interactions": interaction},
        "$set": {"updated_at": now},
    }
    if kind == "recommendation":
        update["$set"]["recommended_action"] = text
    if new_status:
        update["$set"]["status"] = new_status

    db.support_cases.update_one({"case_id": case_id}, update)
    db.interaction_history.insert_one(
        {**interaction, "case_id": case_id, "grower_id": grower_id})
    return interaction
