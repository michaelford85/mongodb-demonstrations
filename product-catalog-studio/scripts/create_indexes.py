#!/usr/bin/env python3
"""Create the Atlas Search + Vector Search indexes for pcs_products.

    python3 scripts/create_indexes.py

Idempotent — safe to re-run. Index builds are async in Atlas; allow 1-2 minutes
before querying. The vector dimension is read from EMBEDDING_DIM and MUST match
the vectors written by seed_data.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo.errors import OperationFailure  # noqa: E402

from lib.atlas_client import PRODUCTS_COLLECTION, db_name, products  # noqa: E402
from lib.embeddings import embedding_dim, provider_name  # noqa: E402
from lib.search import (text_index_definition,  # noqa: E402
                        vector_index_definition)


def _existing(coll) -> dict[str, dict]:
    try:
        return {idx["name"]: idx for idx in coll.list_search_indexes()}
    except Exception:
        return {}


def _create(coll, definition: dict, existing: dict[str, dict]) -> None:
    name = definition["name"]
    current = existing.get(name)
    if current is not None:
        # Reconcile: an index left over from an earlier definition (for example
        # one built before `sku` became searchable) would otherwise be skipped.
        if current.get("latestDefinition") == definition["definition"]:
            print(f"  ✓ Index '{name}' already matches the current definition")
            return
        try:
            coll.update_search_index(name, definition["definition"])
            print(f"  ✓ Updated index '{name}' to the current definition")
        except OperationFailure as e:
            print(f"  WARN: Could not update index '{name}': {e}",
                  file=sys.stderr)
        return
    try:
        coll.create_search_index(definition)
        print(f"  ✓ Created index '{name}' ({definition.get('type', 'search')})")
    except OperationFailure as e:
        print(f"  WARN: Could not create index '{name}': {e}", file=sys.stderr)


def main() -> None:
    coll = products()
    dim = embedding_dim()
    count = coll.count_documents({})
    print(f"Collection {db_name()}.{PRODUCTS_COLLECTION}: {count:,} documents")
    print(f"Embedding provider: {provider_name()} (dim={dim})")
    if count == 0:
        print("WARNING: Collection is empty. Run seed_data.py first.",
              file=sys.stderr)

    existing = _existing(coll)
    print("\nCreating indexes...")
    _create(coll, text_index_definition(), existing)
    _create(coll, vector_index_definition(dim), existing)

    print("\n✓ Done. Atlas builds search indexes asynchronously — allow 1-2 "
          "minutes. Until both are queryable, the search workspace reports the "
          "exact reason instead of silently returning nothing.")
    print("Check status: python3 scripts/status.py")


if __name__ == "__main__":
    main()
