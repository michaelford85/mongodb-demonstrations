from .client import get_collection, get_voyage, VOYAGE_MODEL, EMBEDDING_DIM, QUERY_LIMIT

_INDEX = "product_vector_index"


def semantic_search(query: str, limit: int = QUERY_LIMIT) -> tuple[list[dict], dict]:
    voyage = get_voyage()
    coll = get_collection()

    embedding = voyage.embed(
        texts=[query],
        model=VOYAGE_MODEL,
        input_type="query",
        output_dimension=EMBEDDING_DIM,
    ).embeddings[0]

    pipeline = [
        {
            "$vectorSearch": {
                "index": _INDEX,
                "path": "embedding",
                "queryVector": embedding,
                "numCandidates": limit * 10,
                "limit": limit,
            }
        },
        {"$addFields": {"vector_score": {"$meta": "vectorSearchScore"}}},
        {
            "$project": {
                "asin": 1, "title": 1, "description": 1, "category": 1,
                "price": 1, "rating": 1, "rating_count": 1,
                "image_url": 1, "features": 1, "vector_score": 1,
            }
        },
    ]

    results = list(coll.aggregate(pipeline))
    for r in results:
        r["_id"] = str(r["_id"])
        r["search_score"] = r.get("vector_score", 0)
        r["score_breakdown"] = {"vector (cosine)": round(r.get("vector_score", 0), 6)}

    debug = {
        "index": _INDEX,
        "embedding_model": VOYAGE_MODEL,
        "embedding_dimensions": EMBEDDING_DIM,
        "similarity": "cosine",
        "num_candidates": limit * 10,
        "pipeline_stages": ["$vectorSearch", "$addFields", "$project"],
    }
    return results, debug
