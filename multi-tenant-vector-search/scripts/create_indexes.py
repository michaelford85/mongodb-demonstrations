"""Create the shared flat index and the per-large-tenant HNSW views.

Two regimes, two index strategies, one script:

  1. ONE shared FLAT vector index on the base collection, with `tenant_id` as a
     pre-filter. This serves every small tenant — a filtered exhaustive scan of
     a few-thousand-vector partition is fast and needs no per-tenant index.

  2. For each LARGE tenant: a View scoped to that tenant (`$match` + `$expr`,
     the only form vector-search-on-views supports), then a default HNSW vector
     index built on the view. Big partitions get graph-based ANN; the view
     removes the need for a filter at query time.

Everything is idempotent. Index builds are async — allow 1-2 minutes.

    python scripts/create_indexes.py --profile demo
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo.errors import CollectionInvalid, OperationFailure  # noqa: E402
from pymongo.operations import SearchIndexModel  # noqa: E402

from lib import tenants  # noqa: E402
from lib.client import (  # noqa: E402
    get_db, get_collection, view_name, COLLECTION_NAME,
    FLAT_INDEX, HNSW_INDEX, EMBEDDING_FIELD, TENANT_FIELD, EMBEDDING_DIM, PROFILE,
)


def _existing(coll) -> set:
    try:
        return {ix["name"] for ix in coll.list_search_indexes()}
    except OperationFailure:
        return set()


def _vector_field(indexing_method: str) -> dict:
    return {
        "type": "vector",
        "path": EMBEDDING_FIELD,
        "numDimensions": EMBEDDING_DIM,
        "similarity": "cosine",
        "indexingMethod": indexing_method,
    }


def create_flat_index(coll) -> None:
    if FLAT_INDEX in _existing(coll):
        print(f"Flat index '{FLAT_INDEX}' already exists — skipping.")
        return
    coll.create_search_index(SearchIndexModel(
        name=FLAT_INDEX,
        type="vectorSearch",
        definition={"fields": [
            _vector_field("flat"),
            {"type": "filter", "path": TENANT_FIELD},
        ]},
    ))
    print(f"Created shared FLAT index '{FLAT_INDEX}' on "
          f"'{COLLECTION_NAME}' (pre-filter: {TENANT_FIELD}).")


def create_tenant_view_and_index(db, tenant_id: str) -> None:
    vname = view_name(tenant_id)
    pipeline = [{"$match": {"$expr": {"$eq": [f"${TENANT_FIELD}", tenant_id]}}}]
    try:
        db.create_collection(vname, viewOn=COLLECTION_NAME, pipeline=pipeline)
        print(f"Created view '{vname}' scoped to {TENANT_FIELD}={tenant_id}.")
    except CollectionInvalid:
        print(f"View '{vname}' already exists — skipping create.")

    view = db[vname]
    if HNSW_INDEX in _existing(view):
        print(f"  HNSW index '{HNSW_INDEX}' on '{vname}' already exists — skipping.")
        return
    view.create_search_index(SearchIndexModel(
        name=HNSW_INDEX,
        type="vectorSearch",
        definition={"fields": [_vector_field("hnsw")]},
    ))
    print(f"  Created HNSW index '{HNSW_INDEX}' on view '{vname}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create indexes and tenant views.")
    parser.add_argument("--profile", default=PROFILE, choices=list(tenants.PROFILES))
    args = parser.parse_args()

    coll = get_collection()
    db = get_db()

    if coll.estimated_document_count() == 0:
        print("WARNING: collection is empty. Run scripts/load_data.py first.",
              file=sys.stderr)

    print("── Shared flat index (small tenants) ─────────────────────────────")
    create_flat_index(coll)

    print("\n── Per-tenant HNSW views (large tenants) ─────────────────────────")
    for tid in tenants.large_tenant_ids(args.profile):
        create_tenant_view_and_index(db, tid)

    print("\nAtlas builds indexes asynchronously. Wait 1-2 minutes, then run:")
    print(f"  python scripts/status.py --profile {args.profile}")


if __name__ == "__main__":
    main()
