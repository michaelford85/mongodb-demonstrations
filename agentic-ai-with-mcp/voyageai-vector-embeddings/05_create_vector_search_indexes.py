#!/usr/bin/env python3
"""
Create Atlas Vector Search indexes needed for the demo.

Creates vector search indexes on embedding_voyage_v4 for:
  1) sample_mflix.comments
  2) sample_mflix.movies
  3) mcp_config.agent_memory (optional but recommended)

Notes:
- Uses PyMongo's SearchIndexModel.
- Search index creation is asynchronous; this script only requests creation and polls briefly
  for the index name to become visible.
"""
from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

load_dotenv()

DEFAULT_EMBED_FIELD = "embedding_voyage_v4"
DEFAULT_DIM = 1024


def env(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if not v:
        raise SystemExit(f"Missing required env var: {name}")
    return v


def ensure_vector_index(collection, *, index_name: str, path: str, dims: int) -> None:
    existing = list(collection.list_search_indexes())
    if any(ix.get("name") == index_name for ix in existing):
        print(f"✅ Search index already exists: {collection.full_name} / {index_name}")
        return

    model = SearchIndexModel(
        definition={
            "fields": [
                {
                    "type": "vector",
                    "path": path,
                    "numDimensions": dims,
                    "similarity": "cosine",
                }
            ]
        },
        name=index_name,
        type="vectorSearch",
    )

    print(f"Creating search index: {collection.full_name} / {index_name} ...")
    collection.create_search_index(model=model)

    # Poll briefly so you get quick feedback in a demo.
    for _ in range(30):
        time.sleep(2)
        existing = list(collection.list_search_indexes())
        if any(ix.get("name") == index_name for ix in existing):
            print(f"✅ Index now visible in list_search_indexes(): {index_name}")
            return

    print("⚠️ Index creation requested, but it may still be building. Check Atlas UI or list_search_indexes().")


def main() -> None:
    mongo_uri = env("MONGODB_URI")
    embed_field = os.getenv("EMBEDDING_FIELD", DEFAULT_EMBED_FIELD)
    dims = int(os.getenv("VOYAGE_OUTPUT_DIM", str(DEFAULT_DIM)))

    client = MongoClient(mongo_uri)

    # 1) comments
    comments = client["sample_mflix"]["comments"]
    ensure_vector_index(
        comments,
        index_name=os.getenv("COMMENTS_VECTOR_INDEX", "comments_voyage_v4"),
        path=embed_field,
        dims=dims,
    )

    # 2) movies
    movies = client["sample_mflix"]["movies"]
    ensure_vector_index(
        movies,
        index_name=os.getenv("MOVIES_VECTOR_INDEX", "movies_voyage_v4"),
        path=embed_field,
        dims=dims,
    )

    # 3) memory
    mem_db = os.getenv("MEMORY_DB", "mcp_config")
    mem_coll = os.getenv("MEMORY_COLLECTION", "agent_memory")
    memory = client[mem_db][mem_coll]
    ensure_vector_index(
        memory,
        index_name=os.getenv("MEMORY_VECTOR_INDEX", "memory_voyage_v4"),
        path=embed_field,
        dims=dims,
    )


if __name__ == "__main__":
    main()
