from .client import get_voyage, VOYAGE_RERANK_MODEL, QUERY_LIMIT
from .hybrid import hybrid_search

_FETCH_FACTOR = 3  # retrieve 3× more candidates than needed before reranking


def reranked_search(query: str, limit: int = QUERY_LIMIT) -> tuple[list[dict], dict]:
    voyage = get_voyage()

    candidates, hybrid_debug = hybrid_search(query, limit=limit * _FETCH_FACTOR)
    if not candidates:
        return [], {**hybrid_debug, "rerank_model": VOYAGE_RERANK_MODEL, "candidates_fetched": 0}

    documents = [
        " ".join(filter(None, [
            r.get("title", ""),
            r.get("description", ""),
            " ".join(r.get("features") or []),
        ]))
        for r in candidates
    ]

    rerank_result = voyage.rerank(
        query=query,
        documents=documents,
        model=VOYAGE_RERANK_MODEL,
        top_k=limit,
    )

    reranked = []
    for item in rerank_result.results:
        r = candidates[item.index].copy()
        hybrid_rank = item.index + 1
        rerank_rank = len(reranked) + 1

        r["rerank_score"] = item.relevance_score
        r["original_hybrid_rank"] = hybrid_rank
        r["search_score"] = item.relevance_score
        r["score_breakdown"] = {
            **{k: v for k, v in r.get("score_breakdown", {}).items()},
            "rerank score": round(item.relevance_score, 6),
            "hybrid rank → rerank rank": f"#{hybrid_rank} → #{rerank_rank}",
        }
        reranked.append(r)

    debug = {
        **hybrid_debug,
        "rerank_model": VOYAGE_RERANK_MODEL,
        "candidates_fetched": len(candidates),
        "returned_after_rerank": len(reranked),
        "pipeline_stages": hybrid_debug.get("pipeline_stages", []) + [
            f"voyage.rerank() with {VOYAGE_RERANK_MODEL}",
        ],
    }
    return reranked, debug
