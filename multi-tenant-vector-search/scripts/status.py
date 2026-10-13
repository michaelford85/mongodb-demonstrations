"""Print document counts and the build status of every index and view.

    python scripts/status.py --profile demo

Use this to confirm the shared flat index and each large-tenant HNSW index are
`READY` before querying or benchmarking.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import tenants  # noqa: E402
from lib.client import (  # noqa: E402
    get_db, get_collection, view_name, DB_NAME, COLLECTION_NAME,
    FLAT_INDEX, HNSW_INDEX, TENANT_FIELD, PROFILE,
)


def _status(coll, index_name: str) -> str:
    for ix in coll.list_search_indexes():
        if ix["name"] == index_name:
            return "READY" if ix.get("queryable") else ix.get("status", "UNKNOWN")
    return "MISSING"


def main() -> None:
    parser = argparse.ArgumentParser(description="Show demo status.")
    parser.add_argument("--profile", default=PROFILE, choices=list(tenants.PROFILES))
    args = parser.parse_args()

    coll = get_collection()
    db = get_db()
    total = coll.count_documents({})
    print(f"Namespace: {DB_NAME}.{COLLECTION_NAME}  ({total:,} documents)\n")

    print("── Shared flat index (small tenants) ─────────────────────────────")
    print(f"  {FLAT_INDEX:<28} {_status(coll, FLAT_INDEX)}")

    ready = _status(coll, FLAT_INDEX) == "READY"
    print("\n── Per-tenant HNSW views (large tenants) ─────────────────────────")
    for tid in tenants.large_tenant_ids(args.profile):
        vname = view_name(tid)
        try:
            count = db[vname].count_documents({})
            st = _status(db[vname], HNSW_INDEX)
        except Exception:  # noqa: BLE001 — view may not exist yet
            count, st = 0, "MISSING (view?)"
        ready = ready and st == "READY"
        print(f"  {vname:<28} {st:<16} ({count:,} docs)")

    small = len(tenants.small_tenant_ids(args.profile))
    print(f"\nPre-filter field for the flat index: {TENANT_FIELD} "
          f"({small} small tenants share it)")
    if ready:
        print("All indexes READY. Try: python scripts/query.py --profile "
              f"{args.profile} \"reset my password\"")
    else:
        print("Some indexes still building. Wait ~1-2 minutes and re-run this.")


if __name__ == "__main__":
    main()
