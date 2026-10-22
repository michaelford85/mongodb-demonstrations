"""Drop the test database created by this harness.

Only touches the database named by TEST_DB, and refuses to run unless the name
is confirmed on the command line, so it cannot be pointed at anything else by
accident.

    python3 teardown.py --confirm resilience_test
"""

from __future__ import annotations

import argparse
import os

from pymongo import MongoClient

from common import load_env, require_env


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Drop the test database")
    parser.add_argument("--confirm", required=True,
                        help="Must match TEST_DB exactly")
    args = parser.parse_args()

    db_name = os.getenv("TEST_DB", "resilience_test")
    if args.confirm != db_name:
        raise SystemExit(
            f"Refusing to drop: --confirm '{args.confirm}' does not match "
            f"TEST_DB '{db_name}'"
        )

    client = MongoClient(require_env("TEST_CLUSTER_URI"))
    try:
        collections = client[db_name].list_collection_names()
        client.drop_database(db_name)
        print(f"Dropped {db_name} ({len(collections)} collections: "
              f"{', '.join(collections) or 'none'})")
    finally:
        client.close()

    print("Run artefacts under the results directory are left in place.")


if __name__ == "__main__":
    main()
