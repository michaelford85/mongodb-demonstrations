from .client import get_collection, QUERY_LIMIT

_INDEX = "product_text_index"
_SEARCH_PATHS = ["title", "description", "features_text"]


def keyword_search(query: str, limit: int = QUERY_LIMIT) -> tuple[list[dict], dict]:
    coll = get_collection()

    pipeline = [
        {
            "$search": {
                "index": _INDEX,
                "text": {"query": query, "path": _SEARCH_PATHS},
            }
        },
        {"$addFields": {"text_score": {"$meta": "searchScore"}}},
        {"$limit": limit},
        {
            "$project": {
                "asin": 1, "title": 1, "description": 1, "category": 1,
                "price": 1, "rating": 1, "rating_count": 1,
                "image_url": 1, "features": 1, "text_score": 1,
            }
        },
    ]

    results = list(coll.aggregate(pipeline))
    for r in results:
        r["_id"] = str(r["_id"])
        r["search_score"] = r.get("text_score", 0)
        r["score_breakdown"] = {"text (BM25)": round(r.get("text_score", 0), 6)}

    debug = {
        "index": _INDEX,
        "search_paths": _SEARCH_PATHS,
        "pipeline_stages": ["$search (text)", "$addFields", "$limit", "$project"],
    }
    return results, debug
