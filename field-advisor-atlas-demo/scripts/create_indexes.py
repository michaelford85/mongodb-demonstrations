#!/usr/bin/env python3
"""Create Atlas Vector Search and Atlas Search indexes for knowledge_articles.

Usage:
    python3 scripts/create_indexes.py

Both indexes are idempotent — safe to re-run. Index builds are async in Atlas;
allow 1-2 minutes after running before querying. The vector dimension is read
from EMBEDDING_DIM and MUST match the vectors written by seed_data.py.
"""

import sys
from pathlib import Path

# Allow running as `python3 scripts/create_indexes.py` from the demo root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo.errors import OperationFailure  # noqa: E402

from lib.atlas_client import KNOWLEDGE_COLLECTION, db_name, get_db  # noqa: E402
from lib.embeddings import embedding_dim, provider_name  # noqa: E402
from lib.queries import TEXT_INDEX, VECTOR_INDEX  # noqa: E402


def _existing(coll) -> set[str]:
    try:
        return {idx["name"] for idx in coll.list_search_indexes()}
    except Exception:
        return set()


def create_vector_index(coll, dim: int) -> None:
    if VECTOR_INDEX in _existing(coll):
        print(f"  ✓ Vector index '{VECTOR_INDEX}' already exists")
        return
    index_def = {
        "name": VECTOR_INDEX,
        "type": "vectorSearch",
        "definition": {
            "fields": [
                {"type": "vector", "path": "embedding",
                 "numDimensions": dim, "similarity": "cosine"},
                {"type": "filter", "path": "crop"},
                {"type": "filter", "path": "region"},
                {"type": "filter", "path": "season"},
                {"type": "filter", "path": "product_line"},
                {"type": "filter", "path": "severity"},
            ]
        },
    }
    try:
        coll.create_search_index(index_def)
        print(f"  ✓ Created vector index '{VECTOR_INDEX}' "
              f"(dims={dim}, similarity=cosine)")
    except OperationFailure as e:
        print(f"  WARN: Could not create vector index: {e}", file=sys.stderr)


def create_text_index(coll) -> None:
    if TEXT_INDEX in _existing(coll):
        print(f"  ✓ Text index '{TEXT_INDEX}' already exists")
        return
    index_def = {
        "name": TEXT_INDEX,
        "type": "search",
        "definition": {
            "mappings": {
                "dynamic": False,
                "fields": {
                    "title": {"type": "string", "analyzer": "lucene.english"},
                    "summary": {"type": "string", "analyzer": "lucene.english"},
                    "body": {"type": "string", "analyzer": "lucene.english"},
                    "tags": {"type": "string"},
                    "crop": {"type": "string"},
                    "region": {"type": "string"},
                    "season": {"type": "string"},
                    "product_line": {"type": "string"},
                    "severity": {"type": "string"},
                },
            }
        },
    }
    try:
        coll.create_search_index(index_def)
        print(f"  ✓ Created text index '{TEXT_INDEX}'")
    except OperationFailure as e:
        print(f"  WARN: Could not create text index: {e}", file=sys.stderr)


def main() -> None:
    db = get_db()
    coll = db[KNOWLEDGE_COLLECTION]
    dim = embedding_dim()
    count = coll.count_documents({})
    print(f"Collection {db_name()}.{KNOWLEDGE_COLLECTION}: {count:,} documents")
    print(f"Embedding provider: {provider_name()} (dim={dim})")
    if count == 0:
        print("WARNING: Collection is empty. Run seed_data.py first.",
              file=sys.stderr)

    print("\nCreating indexes...")
    create_vector_index(coll, dim)
    create_text_index(coll)
    print("\n✓ Done. Atlas builds indexes asynchronously — allow 1-2 minutes "
          "before searching. The Atlas Search (keyword) index is optional; the "
          "app falls back to vector-only retrieval if it is not present.")
    print("Next step: streamlit run app.py")


if __name__ == "__main__":
    main()
