#!/usr/bin/env python3
"""
06_cleanup_mcp_demo.py

Cleanup for the Agentic AI + MCP + MongoDB demo:

- Drops the `mcp_config` database (which removes `agent_memory` collection too).
- Unsets the embedding field (EMBEDDING_FIELD) from:
    - sample_mflix.comments
    - sample_mflix.movies
- Removes Atlas Vector Search (Search) indexes:
    - COMMENTS_VECTOR_INDEX (on sample_mflix.comments)
    - MOVIES_VECTOR_INDEX   (on sample_mflix.movies)
    - MEMORY_VECTOR_INDEX   (on mcp_config.agent_memory)

This script loads configuration from a local .env file (same folder as this script).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError


def _env(name: str, default: Optional[str] = None) -> str:
    v = os.getenv(name)
    if v is None or v == "":
        if default is None:
            raise RuntimeError(f"Missing required env var: {name}")
        return default
    return v


@dataclass(frozen=True)
class Cfg:
    mongo_uri: str

    # collections
    comments_db: str
    comments_coll: str
    movies_db: str
    movies_coll: str
    mem_db: str
    mem_coll: str

    # vector search index names (Atlas Search indexes)
    comments_index: str
    movies_index: str
    mem_index: str

    # embedding field
    embedding_field: str


def load_cfg() -> Cfg:
    # Load .env sitting next to this script
    load_dotenv(Path(__file__).with_name(".env"))

    return Cfg(
        mongo_uri=_env("MONGODB_URI"),  # your Atlas connection string

        comments_db=_env("COMMENTS_DB", "sample_mflix"),
        comments_coll=_env("COMMENTS_COLLECTION", "comments"),

        movies_db=_env("MOVIES_DB", "sample_mflix"),
        movies_coll=_env("MOVIES_COLLECTION", "movies"),

        mem_db=_env("MEMORY_DB", "mcp_config"),
        mem_coll=_env("MEMORY_COLLECTION", "agent_memory"),

        comments_index=_env("COMMENTS_VECTOR_INDEX", "comments_voyage_v4"),
        movies_index=_env("MOVIES_VECTOR_INDEX", "movies_voyage_v4"),
        mem_index=_env("MEMORY_VECTOR_INDEX", "memory_voyage_v4"),

        embedding_field=_env("EMBEDDING_FIELD", "embedding_voyage_v4"),
    )


def _safe_list_search_indexes(coll) -> list[str]:
    """
    Return a list of Atlas Search index names on this collection.

    Requires Atlas / MongoDB version supporting $listSearchIndexes.
    """
    try:
        idx_docs = list(coll.list_search_indexes())
        names = []
        for d in idx_docs:
            n = d.get("name")
            if n:
                names.append(n)
        return names
    except Exception:
        # Older pymongo / server: treat as unsupported.
        return []


def _drop_search_index_if_exists(coll, name: str) -> bool:
    """
    Drop an Atlas Search index by name if present. Returns True if dropped.
    """
    existing = _safe_list_search_indexes(coll)
    if existing and name not in existing:
        print(f"  ℹ️  Search indexes on {coll.full_name}: {existing}")
    if existing and name not in existing:
        print(f"  ⚠️  Vector index not found (skipping): {name}")
        return False

    # If existing list was empty, we still *try* to drop; some envs block listing but allow dropping.
    try:
        # PyMongo 4.6+ supports this helper
        coll.drop_search_index(name)
        print(f"  ✅ Dropped vector search index: {name} (collection={coll.full_name})")
        return True
    except AttributeError:
        # Fallback to db.command
        try:
            coll.database.command({"dropSearchIndex": coll.name, "name": name})
            print(f"  ✅ Dropped vector search index: {name} (collection={coll.full_name})")
            return True
        except OperationFailure as e:
            # Common if index does not exist OR feature not supported
            msg = str(e)
            if "IndexNotFound" in msg or "not found" in msg.lower():
                print(f"  ⚠️  Vector index not found (skipping): {name}")
                return False
            raise
    except OperationFailure as e:
        msg = str(e)
        if "IndexNotFound" in msg or "not found" in msg.lower():
            print(f"  ⚠️  Vector index not found (skipping): {name}")
            return False
        # If listing isn't supported, Atlas can return an OperationFailure as well
        raise


def _unset_embedding_field(coll, field: str) -> int:
    """
    Removes the embedding field from all documents. Returns modified count.
    """
    res = coll.update_many({field: {"$exists": True}}, {"$unset": {field: ""}})
    return int(res.modified_count)


def main() -> int:
    cfg = load_cfg()

    print("=== MCP Demo Cleanup ===")
    print(f"Mongo URI: {cfg.mongo_uri.split('@')[-1] if '@' in cfg.mongo_uri else '(redacted)'}")
    print(f"Embedding field: {cfg.embedding_field}")
    print()

    try:
        client = MongoClient(cfg.mongo_uri, serverSelectionTimeoutMS=8000)
        # Force a connection check early.
        client.admin.command("ping")
    except ServerSelectionTimeoutError as e:
        print(f"❌ Could not connect to MongoDB: {e}", file=sys.stderr)
        return 2

    # 1) Drop search indexes (sample_mflix)
    print("=== Dropping Vector Search Indexes ===")
    try:
        comments = client[cfg.comments_db][cfg.comments_coll]
        _drop_search_index_if_exists(comments, cfg.comments_index)
    except Exception as e:
        print(f"  ❌ Failed dropping comments index: {e}", file=sys.stderr)

    try:
        movies = client[cfg.movies_db][cfg.movies_coll]
        _drop_search_index_if_exists(movies, cfg.movies_index)
    except Exception as e:
        print(f"  ❌ Failed dropping movies index: {e}", file=sys.stderr)

    # Memory index is in mcp_config, which we will drop anyway, but we try to drop explicitly first.
    try:
        mem = client[cfg.mem_db][cfg.mem_coll]
        _drop_search_index_if_exists(mem, cfg.mem_index)
    except Exception as e:
        print(f"  ❌ Failed dropping memory index: {e}", file=sys.stderr)

    print()

    # 2) Unset embedding field from comments/movies
    print("=== Removing embedding fields ===")
    try:
        comments = client[cfg.comments_db][cfg.comments_coll]
        n = _unset_embedding_field(comments, cfg.embedding_field)
        print(f"  ✅ Removed '{cfg.embedding_field}' from {cfg.comments_db}.{cfg.comments_coll} -> modified {n} docs")
    except Exception as e:
        print(f"  ❌ Failed unsetting embedding field on comments: {e}", file=sys.stderr)

    try:
        movies = client[cfg.movies_db][cfg.movies_coll]
        n = _unset_embedding_field(movies, cfg.embedding_field)
        print(f"  ✅ Removed '{cfg.embedding_field}' from {cfg.movies_db}.{cfg.movies_coll} -> modified {n} docs")
    except Exception as e:
        print(f"  ❌ Failed unsetting embedding field on movies: {e}", file=sys.stderr)

    print()

    # 3) Drop mcp_config database
    print("=== Dropping database ===")
    try:
        client.drop_database(cfg.mem_db)
        print(f"  ✅ Dropped database: {cfg.mem_db}")
    except Exception as e:
        print(f"  ❌ Failed dropping database {cfg.mem_db}: {e}", file=sys.stderr)

    print("\n✅ Cleanup complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
