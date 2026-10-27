#!/usr/bin/env python3
"""Verify that a seeded/updated PostgreSQL row has reached the Atlas read
model through CDC.

    python scripts/verify_sync.py --id 3            # row must exist and match
    python scripts/verify_sync.py --id 5 --deleted  # row must be absent
    python scripts/verify_sync.py --summary         # counts + freshness
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import atlas_collection, load_config  # noqa: E402
from dms_transform import TABLE_NAME  # noqa: E402


def check_row(collection, row_id: int, expect_deleted: bool) -> bool:
    doc = collection.find_one({"_id": f"knowledge-items-{row_id}"})
    if expect_deleted:
        ok = doc is None
        print(
            f"id={row_id}: {'ABSENT as expected (delete propagated)' if ok
            else 'STILL PRESENT — delete has not propagated yet'}"
        )
        return ok
    if doc is None:
        print(f"id={row_id}: NOT FOUND in Atlas read model yet.")
        return False
    if doc.get("cdc_operation") not in ("load", "insert", "update"):
        print(f"id={row_id}: unexpected cdc_operation={doc.get('cdc_operation')!r}")
        return False
    print(
        f"id={row_id}: OK — operation={doc['cdc_operation']}, "
        f"title={doc.get('title', '')[:60]!r}, "
        f"embedding_dims={len(doc.get('embedding') or [])}, "
        f"source_updated_at={doc.get('source_updated_at')}"
    )
    return True


def summary(collection) -> None:
    total = collection.count_documents({})
    by_op = collection.aggregate(
        [{"$group": {"_id": "$cdc_operation", "n": {"$sum": 1}}}]
    )
    ops = ", ".join(f"{d['_id'] or 'unknown'}: {d['n']}" for d in by_op)
    newest = collection.find_one(
        sort=[("processed_at", -1)], projection={"processed_at": 1}
    )
    lag = ""
    if newest and newest.get("processed_at"):
        age = datetime.now(timezone.utc) - newest["processed_at"]
        lag = f", newest doc ingested {age.total_seconds():.0f}s ago"
    print(f"Read model: {total} docs ({ops}{lag})")


def main() -> None:
    load_config()
    collection = atlas_collection(load_config())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", type=int, help="PostgreSQL primary key to verify.")
    parser.add_argument("--deleted", action="store_true", help="Expect the row to be absent.")
    parser.add_argument("--summary", action="store_true", help="Print counts and freshness.")
    args = parser.parse_args()

    if args.summary or not args.id:
        summary(collection)
    if args.id:
        sys.exit(0 if check_row(collection, args.id, args.deleted) else 1)


if __name__ == "__main__":
    main()
