"""Remove everything the demo created. Idempotent.

Drops each large-tenant HNSW index and its view, then the shared flat index.
Pass --drop-data to also drop the base collection.

    python scripts/teardown.py --profile demo
    python scripts/teardown.py --profile demo --drop-data
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo.errors import OperationFailure  # noqa: E402

from lib import tenants  # noqa: E402
from lib.client import (  # noqa: E402
    get_db, get_collection, view_name, DB_NAME, COLLECTION_NAME,
    FLAT_INDEX, HNSW_INDEX, PROFILE,
)


def _drop_index(coll, name: str, label: str) -> None:
    existing = {ix["name"] for ix in coll.list_search_indexes()}
    if name in existing:
        coll.drop_search_index(name)
        print(f"Dropped {label} index '{name}'.")
    else:
        print(f"{label} index '{name}' not present — skipping.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tear down demo resources.")
    parser.add_argument("--profile", default=PROFILE, choices=list(tenants.PROFILES))
    parser.add_argument("--drop-data", action="store_true",
                        help="also drop the base collection")
    args = parser.parse_args()

    db = get_db()
    coll = get_collection()

    print("── Per-tenant HNSW views ─────────────────────────────────────────")
    for tid in tenants.large_tenant_ids(args.profile):
        vname = view_name(tid)
        try:
            _drop_index(db[vname], HNSW_INDEX, f"HNSW ({vname})")
        except OperationFailure:
            print(f"  view '{vname}' not present — skipping index drop.")
        if vname in db.list_collection_names():
            db[vname].drop()
            print(f"Dropped view '{vname}'.")

    print("\n── Shared flat index ─────────────────────────────────────────────")
    _drop_index(coll, FLAT_INDEX, "flat")

    if args.drop_data:
        coll.drop()
        print(f"\nDropped collection {DB_NAME}.{COLLECTION_NAME}.")
    else:
        print(f"\nLeft data in {DB_NAME}.{COLLECTION_NAME} "
              f"(pass --drop-data to remove it).")


if __name__ == "__main__":
    main()
