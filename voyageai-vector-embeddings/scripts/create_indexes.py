#!/usr/bin/env python3
"""
Create Atlas Vector Search and Atlas Search indexes for the products collection.

Usage:
    python scripts/create_indexes.py

Both indexes are idempotent — safe to re-run. Index builds are async in Atlas;
allow 1-2 minutes after running before querying.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure

load_dotenv(Path(__file__).parent.parent / ".env")

EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))


def get_existing_index_names(coll) -> set[str]:
    try:
        return {idx["name"] for idx in coll.list_search_indexes()}
    except Exception:
        return set()


def create_vector_index(coll, db_name: str, coll_name: str):
    name = "product_vector_index"
    existing = get_existing_index_names(coll)
    if name in existing:
        print(f"  ✓ Vector index '{name}' already exists")
        return

    index_def = {
        "name": name,
        "type": "vectorSearch",
        "definition": {
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": EMBEDDING_DIM,
                    "similarity": "cosine",
                },
                {"type": "filter", "path": "category"},
                {"type": "filter", "path": "price"},
                {"type": "filter", "path": "rating"},
            ]
        },
    }

    try:
        coll.create_search_index(index_def)
        print(f"  ✓ Created vector index '{name}' (dims={EMBEDDING_DIM}, similarity=cosine)")
    except OperationFailure as e:
        print(f"  WARN: Could not create vector index: {e}", file=sys.stderr)


def create_text_index(coll, db_name: str, coll_name: str):
    name = "product_text_index"
    existing = get_existing_index_names(coll)
    if name in existing:
        print(f"  ✓ Text index '{name}' already exists")
        return

    index_def = {
        "name": name,
        "type": "search",
        "definition": {
            "mappings": {
                "dynamic": False,
                "fields": {
                    "title": {"type": "string", "analyzer": "lucene.english"},
                    "description": {"type": "string", "analyzer": "lucene.english"},
                    "features_text": {"type": "string", "analyzer": "lucene.english"},
                    "category": {"type": "string"},
                    "price": {"type": "number"},
                    "rating": {"type": "number"},
                },
            }
        },
    }

    try:
        coll.create_search_index(index_def)
        print(f"  ✓ Created text index '{name}'")
    except OperationFailure as e:
        print(f"  WARN: Could not create text index: {e}", file=sys.stderr)


def main():
    uri = os.getenv("MONGODB_URI")
    cert = os.getenv("MONGODB_CERT")
    db_name = os.getenv("DB_NAME", "ecommerce_demo")
    coll_name = os.getenv("COLLECTION_NAME", "products")

    if cert:
        mongo = MongoClient(uri, tls=True, tlsCertificateKeyFile=cert)
    else:
        mongo = MongoClient(uri)

    coll = mongo[db_name][coll_name]
    doc_count = coll.count_documents({})
    print(f"Collection {db_name}.{coll_name}: {doc_count:,} documents")

    if doc_count == 0:
        print("WARNING: Collection is empty. Run scripts/load_data.py first.", file=sys.stderr)

    print("\nCreating indexes...")
    create_vector_index(coll, db_name, coll_name)
    create_text_index(coll, db_name, coll_name)

    print("\n✓ Done. Atlas builds indexes asynchronously — allow 1-2 minutes before searching.")
    print("Next step: python scripts/add_embeddings.py")


if __name__ == "__main__":
    main()
