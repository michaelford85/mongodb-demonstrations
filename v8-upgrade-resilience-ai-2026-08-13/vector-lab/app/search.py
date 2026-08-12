"""The three search strategies, each returning results plus the pipeline used.

    keyword  $search        BM25 over title and body. Matches words.
    vector   $vectorSearch  cosine over client-side embeddings. Matches meaning.
    rerank   $vectorSearch (oversampled) then a cross-encoder over the candidates.

Every function returns the same shape so the UI can render them identically and
the pipeline can be shown alongside the results.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: E402
import embeddings  # noqa: E402
import rerank as rerank_mod  # noqa: E402

MODES = ("keyword", "vector", "rerank")

_PROJECT = {
    "_id": 0,
    "doc_id": 1,
    config.TITLE_FIELD: 1,
    config.BODY_FIELD: 1,
    "category": 1,
    "product": 1,
    "kind": 1,
}


def snippet(text: str, chars: int = None) -> str:
    chars = chars or config.SNIPPET_CHARS
    text = " ".join((text or "").split())
    return text if len(text) <= chars else text[:chars].rstrip() + "…"


def _result(doc: dict, rank: int, score: float, score_label: str) -> dict:
    return {
        "rank": rank,
        "doc_id": doc.get("doc_id"),
        "title": doc.get(config.TITLE_FIELD, ""),
        "snippet": snippet(doc.get(config.BODY_FIELD, "")),
        "category": doc.get("category"),
        "product": doc.get("product"),
        "kind": doc.get("kind"),
        "score": round(score, 6) if score is not None else None,
        "score_label": score_label,
        "moved_from": doc.get("vector_rank"),
    }


def _keyword_pipeline(query: str, limit: int) -> list:
    return [
        {
            "$search": {
                "index": config.TEXT_INDEX,
                "text": {
                    "query": query,
                    "path": [config.TITLE_FIELD, config.BODY_FIELD],
                },
            }
        },
        {"$limit": limit},
        {"$project": {**_PROJECT, "score": {"$meta": "searchScore"}}},
    ]


def _vector_pipeline(vector: list, limit: int) -> list:
    return [
        {
            "$vectorSearch": {
                "index": config.VECTOR_INDEX,
                "path": config.EMBEDDING_FIELD,
                "queryVector": vector,
                "numCandidates": limit * config.NUM_CANDIDATES_MULTIPLIER,
                "limit": limit,
            }
        },
        {"$project": {**_PROJECT, "score": {"$meta": "vectorSearchScore"}}},
    ]


def _redacted_vector_pipeline(pipeline: list, dims: int) -> list:
    """The same pipeline with the query vector replaced by a placeholder, so it
    can be displayed without dumping a thousand floats into the page."""
    shown = []
    for stage in pipeline:
        if "$vectorSearch" in stage:
            vs = dict(stage["$vectorSearch"])
            vs["queryVector"] = f"<{dims} floats from {config.EMBEDDING_PROVIDER}>"
            shown.append({"$vectorSearch": vs})
        else:
            shown.append(stage)
    return shown


def keyword_search(query: str, limit: int = None) -> dict:
    limit = limit or config.RESULT_LIMIT
    pipeline = _keyword_pipeline(query, limit)
    started = time.perf_counter()
    docs = list(config.get_articles().aggregate(pipeline))
    elapsed = (time.perf_counter() - started) * 1000
    return {
        "mode": "keyword",
        "label": "Keyword — Atlas Search BM25",
        "explanation": "Ranks documents by the query's words. A page that never "
                       "uses those words cannot be found, however well it "
                       "answers the question.",
        "results": [_result(d, i, d.get("score"), "searchScore")
                    for i, d in enumerate(docs, start=1)],
        "pipeline": pipeline,
        "elapsed_ms": round(elapsed, 1),
        "backend": "Atlas Search",
    }


def vector_search(query: str, limit: int = None) -> dict:
    limit = limit or config.RESULT_LIMIT
    started = time.perf_counter()
    vector = embeddings.embed_query(query)
    embed_ms = (time.perf_counter() - started) * 1000
    pipeline = _vector_pipeline(vector, limit)
    query_started = time.perf_counter()
    docs = list(config.get_articles().aggregate(pipeline))
    elapsed = (time.perf_counter() - query_started) * 1000
    return {
        "mode": "vector",
        "label": "Vector — $vectorSearch (cosine)",
        "explanation": "Ranks by proximity in embedding space, so wording no "
                       "longer has to match. Related-but-wrong documents can "
                       "still crowd the top of the list.",
        "results": [_result(d, i, d.get("score"), "vectorSearchScore")
                    for i, d in enumerate(docs, start=1)],
        "pipeline": _redacted_vector_pipeline(pipeline, len(vector)),
        "elapsed_ms": round(elapsed, 1),
        "embed_ms": round(embed_ms, 1),
        "backend": f"Atlas Vector Search + {config.EMBEDDING_PROVIDER} embeddings",
    }


def rerank_search(query: str, limit: int = None) -> dict:
    limit = limit or config.RESULT_LIMIT
    candidate_count = max(config.RERANK_CANDIDATES, limit)

    started = time.perf_counter()
    vector = embeddings.embed_query(query)
    embed_ms = (time.perf_counter() - started) * 1000

    pipeline = _vector_pipeline(vector, candidate_count)
    query_started = time.perf_counter()
    candidates = list(config.get_articles().aggregate(pipeline))
    search_ms = (time.perf_counter() - query_started) * 1000

    rerank_started = time.perf_counter()
    ordered = rerank_mod.rerank(query, candidates, limit)
    rerank_ms = (time.perf_counter() - rerank_started) * 1000

    return {
        "mode": "rerank",
        "label": f"Vector + Rerank — {rerank_mod.backend()} cross-encoder",
        "explanation": f"Takes the top {candidate_count} vector candidates and "
                       f"scores each one against the query directly, then keeps "
                       f"the best {limit}. Too slow to search with, ideal for "
                       f"reordering.",
        "results": [_result(d, i, d.get("rerank_score"), "rerankScore")
                    for i, d in enumerate(ordered, start=1)],
        "pipeline": _redacted_vector_pipeline(pipeline, len(vector)),
        "elapsed_ms": round(search_ms, 1),
        "embed_ms": round(embed_ms, 1),
        "rerank_ms": round(rerank_ms, 1),
        "candidates": candidate_count,
        "backend": f"Atlas Vector Search + {rerank_mod.backend()} rerank",
    }


def run(mode: str, query: str, limit: int = None) -> dict:
    if mode == "keyword":
        return keyword_search(query, limit)
    if mode == "vector":
        return vector_search(query, limit)
    if mode == "rerank":
        return rerank_search(query, limit)
    raise ValueError(f"unknown mode '{mode}'; expected one of {MODES}")
