#!/usr/bin/env python3
"""Remove ONLY demo-owned data: the Atlas demo database collections/indexes,
the PostgreSQL demo table, and local generated files.

Never touches the Atlas cluster, other databases, or Terraform resources
(see `terraform destroy` in the README for AWS teardown).

    python scripts/cleanup_demo.py            # dry run: shows what would happen
    python scripts/cleanup_demo.py --yes      # actually delete
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import load_config  # noqa: E402


def main() -> None:
    cfg = load_config()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="Required to actually delete anything.")
    args = parser.parse_args()

    print("Demo-owned items that would be removed:")
    print(f"  Atlas db '{cfg['database']}' (collections: {cfg['collection']}, dlq_items) and its search index")
    print(f"  PostgreSQL table '{cfg['pg']['schema']}.{cfg['pg']['table']}' (data only; table kept)")
    print("  Local: logs/, .pytest_cache/ in this demo folder")
    print("NOT removed: the Atlas cluster, any other database, or any AWS resource.")

    if not args.yes:
        print("\nDry run only. Re-run with --yes to delete.")
        return

    # 1. Atlas demo database (scoped to ATLAS_DATABASE only).
    import pymongo

    client = pymongo.MongoClient(cfg["atlas_uri"])
    db = client[cfg["database"]]
    try:
        for coll in db.list_collection_names():
            db[coll].drop()
            print(f"Dropped Atlas collection {cfg['database']}.{coll}")
        client.drop_database(cfg["database"])
        print(f"Dropped Atlas database '{cfg['database']}'.")
    finally:
        client.close()

    # 2. PostgreSQL demo rows (table/schema kept for re-seeding).
    import psycopg2

    conn = psycopg2.connect(
        host=cfg["pg"]["host"],
        port=cfg["pg"]["port"],
        dbname=cfg["pg"]["dbname"],
        user=cfg["pg"]["user"],
        password=cfg["pg"]["password"],
        sslmode="require",
        connect_timeout=15,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"TRUNCATE {cfg['pg']['schema']}.{cfg['pg']['table']} RESTART IDENTITY CASCADE"
            )
        conn.commit()
        print(f"Truncated PostgreSQL table {cfg['pg']['schema']}.{cfg['pg']['table']}.")
    finally:
        conn.close()

    # 3. Local generated files.
    demo_root = Path(__file__).parent.parent
    for rel in ("logs", ".pytest_cache"):
        import shutil

        target = demo_root / rel
        if target.exists():
            shutil.rmtree(target)
            print(f"Removed local {rel}/")

    print("Cleanup complete.")


if __name__ == "__main__":
    main()
