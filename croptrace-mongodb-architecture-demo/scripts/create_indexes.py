#!/usr/bin/env python3
"""Create the Atlas Vector Search index for knowledge_notes.

    python3 scripts/create_indexes.py

Idempotent — safe to re-run. Index builds are async in Atlas; allow 1-2 minutes
before querying. The vector dimension is read from EMBEDDING_DIM and MUST match
the vectors written by seed_data.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo.errors import OperationFailure  # noqa: E402

from lib.atlas_client import KNOWLEDGE_COLLECTION, db_name, get_db  # noqa: E402
from lib.embeddings import embedding_dim, provider_name  # noqa: E402
from lib.queries import VECTOR_INDEX  # noqa: E402


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
                {"type": "filter", "path": "category"},
            ]
        },
    }
    try:
        coll.create_search_index(index_def)
        print(f"  ✓ Created vector index '{VECTOR_INDEX}' "
              f"(dims={dim}, similarity=cosine)")
    except OperationFailure as e:
        print(f"  WARN: Could not create vector index: {e}", file=sys.stderr)


def main() -> None:
    coll = get_db()[KNOWLEDGE_COLLECTION]
    dim = embedding_dim()
    count = coll.count_documents({})
    print(f"Collection {db_name()}.{KNOWLEDGE_COLLECTION}: {count:,} documents")
    print(f"Embedding provider: {provider_name()} (dim={dim})")
    if count == 0:
        print("WARNING: Collection is empty. Run seed_data.py first.",
              file=sys.stderr)

    print("\nCreating index...")
    create_vector_index(coll, dim)
    print("\n✓ Done. Atlas builds the index asynchronously — allow 1-2 minutes. "
          "Until it is queryable, the Knowledge Assistant falls back to an "
          "in-app cosine scan so the demo still works.")
    print("Check status: python3 scripts/status.py")


if __name__ == "__main__":
    main()
