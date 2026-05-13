from .client import (
    get_collection, get_voyage, get_collection_name,
    VOYAGE_MODEL, EMBEDDING_DIM, QUERY_LIMIT,
)

_VECTOR_INDEX = "product_vector_index"
_TEXT_INDEX = "product_text_index"
_TEXT_PATHS = ["title", "description", "features_text"]

# Standard RRF smoothing constant — higher k = gentler rank penalty
RRF_K = 60

_PRODUCT_FIELDS = ["title", "asin", "description", "category",
                   "price", "rating", "rating_count", "image_url", "features"]


def _product_projection(score_field: str) -> dict:
    proj = {k: f"$docs.{k}" for k in _PRODUCT_FIELDS}
    proj["_id"] = "$docs._id"
    proj[score_field] = 1
    return {"$project": proj}


def hybrid_search(query: str, limit: int = QUERY_LIMIT) -> tuple[list[dict], dict]:
    voyage = get_voyage()
    coll = get_collection()
    coll_name = get_collection_name()

    embedding = voyage.embed(
        texts=[query],
        model=VOYAGE_MODEL,
        input_type="query",
        output_dimension=EMBEDDING_DIM,
    ).embeddings[0]

    overrequest = limit * 10

    pipeline = [
        # ── Vector search leg ────────────────────────────────────────────────
        {
            "$vectorSearch": {
                "index": _VECTOR_INDEX,
                "path": "embedding",
                "queryVector": embedding,
                "numCandidates": overrequest,
                "limit": overrequest,
            }
        },
        {"$group": {"_id": None, "docs": {"$push": "$$ROOT"}}},
        {"$unwind": {"path": "$docs", "includeArrayIndex": "rank"}},
        {"$addFields": {"vs_score": {"$divide": [1.0, {"$add": ["$rank", RRF_K]}]}}},
        _product_projection("vs_score"),

        # ── Text search leg (via $unionWith) ─────────────────────────────────
        {
            "$unionWith": {
                "coll": coll_name,
                "pipeline": [
                    {
                        "$search": {
                            "index": _TEXT_INDEX,
                            "text": {"query": query, "path": _TEXT_PATHS},
                        }
                    },
                    {"$limit": overrequest},
                    {"$group": {"_id": None, "docs": {"$push": "$$ROOT"}}},
                    {"$unwind": {"path": "$docs", "includeArrayIndex": "rank"}},
                    {"$addFields": {"ts_score": {"$divide": [1.0, {"$add": ["$rank", RRF_K]}]}}},
                    _product_projection("ts_score"),
                ],
            }
        },

        # ── Merge and rank ───────────────────────────────────────────────────
        {
            "$group": {
                "_id": "$_id",
                "vs_score": {"$max": "$vs_score"},
                "ts_score": {"$max": "$ts_score"},
                **{k: {"$first": f"${k}"} for k in _PRODUCT_FIELDS},
            }
        },
        {
            "$addFields": {
                "score": {
                    "$add": [
                        {"$ifNull": ["$vs_score", 0]},
                        {"$ifNull": ["$ts_score", 0]},
                    ]
                }
            }
        },
        {"$sort": {"score": -1}},
        {"$limit": limit},
    ]

    results = list(coll.aggregate(pipeline))
    for r in results:
        r["_id"] = str(r["_id"])
        r["search_score"] = r.get("score", 0)
        r["score_breakdown"] = {
            "vector (RRF)": round(r.get("vs_score") or 0, 6),
            "text (RRF)": round(r.get("ts_score") or 0, 6),
            "combined": round(r.get("score") or 0, 6),
        }

    debug = {
        "approach": "Reciprocal Rank Fusion (RRF)",
        "rrf_k": RRF_K,
        "vector_index": _VECTOR_INDEX,
        "text_index": _TEXT_INDEX,
        "embedding_model": VOYAGE_MODEL,
        "pipeline_stages": [
            "$vectorSearch → rank → RRF score",
            "$unionWith ($search → rank → RRF score)",
            "$group (merge) → $sort → $limit",
        ],
    }
    return results, debug
