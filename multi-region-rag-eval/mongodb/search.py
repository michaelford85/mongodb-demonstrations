"""Atlas Vector Search query with optional metadata pre-filter."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import load_settings  # noqa: E402
from embeddings import embed_account  # noqa: E402


def search(
    query_account: str,
    product_group: str,
    region: str | None,
    k: int = 5,
) -> tuple[list[dict[str, Any]], float]:
    settings = load_settings()
    query_vec = embed_account(query_account, product_group, settings.embed_dim)

    vector_stage: dict[str, Any] = {
        "$vectorSearch": {
            "index": settings.atlas_vector_index,
            "path": "embedding",
            "queryVector": query_vec,
            "numCandidates": max(100, k * 20),
            "limit": k,
        }
    }
    # Native pre-filter: the Atlas Vector Search engine restricts the candidate
    # set to documents matching the filter *before* scoring similarities.
    if region:
        vector_stage["$vectorSearch"]["filter"] = {"region": {"$eq": region}}

    pipeline = [
        vector_stage,
        {
            "$project": {
                "_id": 0,
                "account_name": 1,
                "product_group": 1,
                "region": 1,
                "sales_area": 1,
                "service_agent_id": 1,
                "operational_identity": 1,
                "similarity": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    client = MongoClient(settings.mongo_uri)
    coll = client[settings.mongo_db][settings.mongo_collection]
    start = time.perf_counter()
    results = list(coll.aggregate(pipeline))
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return results, elapsed_ms


def _format(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(no matches)"
    lines = []
    for r in rows:
        lines.append(
            f"  {r['similarity']:.4f}  {r['account_name']:<32} "
            f"region={r['region']:<8} agent={r['service_agent_id']} "
            f"area={r['sales_area']}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True,
                        help="Incoming (possibly misspelled) account name.")
    parser.add_argument("--product", default="Software")
    parser.add_argument("--region", default=None,
                        help="Optional pre-filter region (e.g. France).")
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()

    rows, elapsed = search(args.query, args.product, args.region, args.k)
    print(f"Atlas Vector Search results in {elapsed:.1f} ms "
          f"(region pre-filter: {args.region or 'none'})")
    print(_format(rows))


if __name__ == "__main__":
    main()
