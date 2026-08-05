"""The search strategies the lab compares.

Each function returns (results, pipeline). The `pipeline` is the EXACT
aggregation the GUI just ran against Atlas — the app renders it as a
copy-pasteable mongosh snippet so you can reproduce every result yourself.

Because the vector index uses Automated Embedding (autoEmbed), the semantic
and hybrid legs pass plain query text to $vectorSearch via the `query`
option. Atlas embeds it server-side. No vectors ever touch this code.

The optional rerank strategy layers a Voyage AI cross-encoder on top of the
hybrid results — that final re-scoring runs client-side and is the one step
that cannot be reproduced in mongosh.
"""
from lib.client import (
    get_collection, get_voyage, VECTOR_INDEX, TEXT_INDEX, EMBEDDING_MODEL,
    VOYAGE_RERANK_MODEL, SEARCH_FIELD, QUERY_LIMIT,
)

_PROJECT_FIELDS = {"_id": 0, "title": 1, "year": 1, "genres": 1, SEARCH_FIELD: 1}


def _vector_stage(query: str, limit: int) -> dict:
    """A $vectorSearch stage driven by autoEmbed (plain-text `query`)."""
    return {
        "$vectorSearch": {
            "index": VECTOR_INDEX,
            "path": SEARCH_FIELD,
            "query": query,
            "model": EMBEDDING_MODEL,
            "numCandidates": max(limit * 10, 100),
            "limit": limit,
        }
    }


def _text_stage(query: str) -> dict:
    return {
        "$search": {
            "index": TEXT_INDEX,
            "text": {"query": query, "path": SEARCH_FIELD},
        }
    }


def keyword_search(query: str, limit: int = QUERY_LIMIT):
    """Classic BM25 — matches literal words in the plot."""
    pipeline = [
        _text_stage(query),
        {"$limit": limit},
        {"$project": {**_PROJECT_FIELDS, "score": {"$meta": "searchScore"}}},
    ]
    return list(get_collection().aggregate(pipeline)), pipeline


def semantic_search(query: str, limit: int = QUERY_LIMIT):
    """Vector search over autoEmbed — matches meaning, not words."""
    pipeline = [
        _vector_stage(query, limit),
        {"$project": {**_PROJECT_FIELDS, "score": {"$meta": "vectorSearchScore"}}},
    ]
    return list(get_collection().aggregate(pipeline)), pipeline


def hybrid_search(query: str, limit: int = QUERY_LIMIT):
    """Reciprocal-rank fusion of the semantic and keyword legs via $rankFusion.

    Atlas runs both input pipelines, ranks each independently, then fuses the
    ranks. Weights let you dial how much each leg contributes.
    """
    pipeline = [
        {
            "$rankFusion": {
                "input": {
                    "pipelines": {
                        "semantic": [_vector_stage(query, limit)],
                        "keyword": [_text_stage(query), {"$limit": limit}],
                    }
                },
                "combination": {"weights": {"semantic": 1.0, "keyword": 1.0}},
                "scoreDetails": True,
            }
        },
        {"$limit": limit},
        {
            "$project": {
                **_PROJECT_FIELDS,
                "score": {"$meta": "score"},
                "scoreDetails": {"$meta": "scoreDetails"},
            }
        },
    ]
    return list(get_collection().aggregate(pipeline)), pipeline


RERANK_FETCH_FACTOR = 3  # fetch this many × the requested results, then rerank


def rerank_search(query: str, limit: int = QUERY_LIMIT):
    """Two-stage retrieval: hybrid fetches a wide candidate set, then a Voyage AI
    cross-encoder re-scores each candidate directly against the query.

    The rerank step runs CLIENT-SIDE via the Voyage API, so — unlike the other
    strategies — it cannot be reproduced in mongosh. The returned `pipeline` is
    the hybrid retrieval query that feeds the reranker. Each result carries its
    `hybrid_rank` and `rerank_rank` so you can see how far the reranker moved it.
    """
    candidates, pipeline = hybrid_search(query, limit=limit * RERANK_FETCH_FACTOR)
    if not candidates:
        return [], pipeline

    reranked = get_voyage().rerank(
        query=query,
        documents=[c.get(SEARCH_FIELD, "") for c in candidates],
        model=VOYAGE_RERANK_MODEL,
        top_k=limit,
    )

    results = []
    for new_rank, item in enumerate(reranked.results, start=1):
        doc = dict(candidates[item.index])
        doc["hybrid_rank"] = item.index + 1
        doc["rerank_rank"] = new_rank
        doc["score"] = item.relevance_score
        results.append(doc)
    return results, pipeline
