#!/usr/bin/env python3
"""One-time, demo-scoped setup for the optional semantic retrieval path.

Creates the Atlas Vector Search index with an ``autoEmbed`` field on THIS
demo's change_notes collection ONLY. Requires MONGODB_URI to point at an
Atlas cluster (Automated Embedding is an Atlas feature). The index is
idempotent — safe to re-run; it never modifies existing indexes or any
other collection/database.

Usage:
    PYTHONPATH=src python scripts/create_vector_index.py
"""

import os
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_change_ops_agent.vector_search import VECTOR_INDEX_NAME, index_definition  # noqa: E402


def main() -> int:
    load_dotenv(find_dotenv(usecwd=True))
    uri = os.environ.get("MONGODB_URI", "")
    database = os.environ.get("MONGODB_DATABASE", "change_ops_demo")
    if not uri:
        print("MONGODB_URI is empty: semantic retrieval is optional; mock mode uses keyword fallback.")
        print("Set MONGODB_URI to an existing Atlas cluster to create the demo index.")
        return 1
    if "mongodb+srv" not in uri and "mongodb.net" not in uri:
        print(
            "MONGODB_URI does not look like an Atlas connection string. Automated Embedding "
            "requires an Atlas cluster; refusing to create the index elsewhere."
        )
        return 1

    collection_name = "change_notes"
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    collection = client[database][collection_name]

    existing = {idx.get("name") for idx in collection.list_search_indexes()}
    if VECTOR_INDEX_NAME in existing:
        print(f"Index '{VECTOR_INDEX_NAME}' already exists on {database}.{collection_name}; nothing to do.")
        return 0

    try:
        collection.create_search_index(index_definition())
        print(f"Created index '{VECTOR_INDEX_NAME}' on {database}.{collection_name}.")
        print("Index builds are async in Atlas; allow 1-2 minutes before querying.")
        return 0
    except OperationFailure as exc:
        print(f"WARN: Could not create vector index: {exc}", file=sys.stderr)
        print(
            "Hint: Automated Embedding requires an Atlas cluster with Vector Search enabled "
            "and a driver/server version that supports the autoEmbed field type."
        )
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
