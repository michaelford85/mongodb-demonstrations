"""Demonstrate the vector-index-per-container limits on each backend.

Cosmos DB for NoSQL caps vector paths per container at 10, and the
vector embedding policy is immutable once the container holds data, so
the cap is effectively a design-time constraint. MongoDB Atlas allows
many independent vectorSearch indexes on a single collection (the
practical cluster-wide limit is in the thousands).

This script proves the difference programmatically against your live
cluster:

  1. Tries to create a temporary Cosmos container with 11 vector paths.
     Expected: the create call is rejected by the service.
  2. Creates 11 distinct Atlas vectorSearch indexes on a temporary
     collection. Expected: all 11 create calls succeed.
  3. Cleans up the temporary container and the temporary indexes.

Usage:
    python -m compare.index_limits
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosHttpResponseError
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import load_settings  # noqa: E402

ATLAS_TEMPLATE = Path(__file__).resolve().parent.parent / "mongodb" / "atlas_index.json"

# Cosmos NoSQL documented limit (Microsoft Learn, "Vector Search policy
# limits"): up to 10 vector paths per container.
COSMOS_VECTOR_PATH_LIMIT = 10


def _build_vector_policy(num_paths: int, dim: int) -> tuple[dict, dict]:
    vector_embeddings = [
        {
            "path": f"/vec_{i}",
            "dataType": "float32",
            "distanceFunction": "cosine",
            "dimensions": dim,
        }
        for i in range(num_paths)
    ]
    vector_indexes = [{"path": f"/vec_{i}", "type": "diskANN"} for i in range(num_paths)]
    indexing_policy = {
        "indexingMode": "consistent",
        "includedPaths": [{"path": "/*"}],
        "excludedPaths": [{"path": f"/vec_{i}/*"} for i in range(num_paths)],
        "vectorIndexes": vector_indexes,
    }
    return {"vectorEmbeddings": vector_embeddings}, indexing_policy


def demo_cosmos(over_limit: int) -> None:
    settings = load_settings()
    cosmos = CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
    database = cosmos.get_database_client(settings.cosmos_database)
    name = "compare_index_limits_tmp"

    # Sweep down from over_limit until the create succeeds; the highest
    # accepted value is the effective cap reported by the service.
    accepted_count: int | None = None
    rejection_message: str | None = None
    for count in range(over_limit, 0, -1):
        vector_policy, indexing_policy = _build_vector_policy(count, settings.embed_dim)
        try:
            database.create_container(
                id=name,
                partition_key=PartitionKey(path="/document_id"),
                vector_embedding_policy=vector_policy,
                indexing_policy=indexing_policy,
            )
            accepted_count = count
            print(f"[cosmos] container with {count} vector paths created.")
            break
        except CosmosHttpResponseError as exc:
            if rejection_message is None:
                rejection_message = f"HTTP {exc.status_code}: {exc.message.splitlines()[0]}"
            print(f"[cosmos] {count} vector paths rejected.")
        except TypeError as exc:
            raise SystemExit(
                "azure-cosmos SDK is too old to accept vector_embedding_policy. "
                "Run `pip install -U azure-cosmos` (>=4.7.0)."
            ) from exc

    if accepted_count is not None:
        try:
            database.delete_container(name)
        except Exception:  # noqa: BLE001
            pass

    print(
        f"[cosmos] highest accepted vector paths = {accepted_count}; "
        f"first rejection: {rejection_message}"
    )


def demo_atlas(num_indexes: int) -> None:
    settings = load_settings()
    template = json.loads(ATLAS_TEMPLATE.read_text(encoding="utf-8"))
    client = MongoClient(settings.mongo_uri)
    coll = client[settings.mongo_db]["compare_index_limits_tmp"]

    # Ensure the collection exists so create_search_index has a target.
    coll.insert_one({"_id": "seed", "embedding": [0.0] * settings.embed_dim})

    created: list[str] = []
    try:
        for i in range(num_indexes):
            name = f"tmp_compare_idx_{i:02d}"
            coll.create_search_index(
                model=SearchIndexModel(
                    name=name,
                    type=template.get("type", "vectorSearch"),
                    definition=template["definition"],
                )
            )
            created.append(name)
            print(f"[atlas] submitted index {i + 1}/{num_indexes}: {name}")
        print(
            f"[atlas] all {num_indexes} create_search_index calls succeeded. "
            "Atlas will build them asynchronously."
        )
    finally:
        for name in created:
            try:
                coll.drop_search_index(name)
            except Exception:  # noqa: BLE001
                pass
        # Give Atlas a moment to register the drops, then remove the seed.
        time.sleep(2.0)
        coll.drop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--over-limit", type=int, default=COSMOS_VECTOR_PATH_LIMIT + 1)
    parser.add_argument("--atlas-count", type=int, default=COSMOS_VECTOR_PATH_LIMIT + 1)
    parser.add_argument("--only", choices=("cosmos", "atlas", "both"), default="both")
    args = parser.parse_args()

    if args.only in ("cosmos", "both"):
        demo_cosmos(args.over_limit)
    if args.only in ("atlas", "both"):
        demo_atlas(args.atlas_count)


if __name__ == "__main__":
    main()
