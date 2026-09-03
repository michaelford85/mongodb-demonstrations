"""Tear down the Northstar Payments Command Center demo.

Drops any Atlas Search indexes on the demo collections, drops the demo database
(collections and their indexes included), and frees the local Streamlit port.
Only touches this demo's database — no other database on the cluster is
affected. Asks for confirmation before deleting.

    python3 teardown.py                  # prompts, then tears everything down
    python3 teardown.py --yes            # no prompt
    python3 teardown.py --keep-db        # only drop search indexes + free port
    python3 teardown.py --clear-zone-ranges  # also remove per-region zone ranges
    python3 teardown.py --port 8502      # override the Streamlit port to free
"""

import argparse
import os
import signal
import subprocess

from bson import MaxKey, MinKey
from pymongo.errors import OperationFailure, PyMongoError

from lib.atlas_client import (COLLECTIONS, REGIONS, SHARD_KEYS, ZONE_BY_REGION,
                              db_name, get_client, get_db, is_mongos)


def _default_port() -> int:
    return int(os.getenv("STREAMLIT_SERVER_PORT", "8501"))


def clear_zone_ranges() -> None:
    """Best-effort removal of the per-region zone key ranges we created.

    Dropping the database already discards sharding config and zone ranges, so
    this is only useful with --keep-db. The Atlas zone↔shard attachments
    themselves are cluster topology (managed by Atlas) and are left intact.
    """
    if not is_mongos():
        print("  · Not a sharded cluster — no zone ranges to clear")
        return
    client, name = get_client(), db_name()
    cleared = 0
    for coll, key in SHARD_KEYS.items():
        second = list(key.keys())[1]
        ns = f"{name}.{coll}"
        for region in REGIONS:
            lo = {"region": region, second: MinKey()}
            hi = {"region": region, second: MaxKey()}
            try:
                client.admin.command("updateZoneKeyRange", ns, min=lo, max=hi,
                                     zone=None)
                cleared += 1
            except OperationFailure:
                pass  # range may already be gone
    print(f"  ✓ Cleared {cleared} zone key range(s) across "
          f"{len(ZONE_BY_REGION)} zones")


def drop_search_indexes() -> None:
    """Best-effort drop of any Atlas Search indexes on the demo collections.

    The seed script only builds regular btree indexes (removed when the
    database is dropped), but this also cleans up an optional Atlas Search
    index if one was added as an extension.
    """
    db = get_db()
    found = 0
    for coll_name in COLLECTIONS:
        coll = db[coll_name]
        try:
            names = [idx["name"] for idx in coll.list_search_indexes()]
        except PyMongoError:
            names = []
        for name in names:
            try:
                coll.drop_search_index(name)
                print(f"  ✓ Dropped search index '{name}' on '{coll_name}'")
                found += 1
            except OperationFailure as e:
                print(f"  WARN: Could not drop '{name}' on '{coll_name}': {e}")
    if not found:
        print("  · No Atlas Search indexes to drop")


def drop_demo_database() -> None:
    """Drop the whole demo database (all collections and their indexes)."""
    client = get_client()
    name = db_name()
    client.drop_database(name)
    print(f"  ✓ Dropped database '{name}' "
          f"({len(COLLECTIONS)} demo collections)")


def free_port(port: int) -> None:
    """Kill any local process listening on the Streamlit port."""
    try:
        out = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}"],
            capture_output=True, text=True, check=False)
    except FileNotFoundError:
        print(f"  · 'lsof' not available — free port {port} manually if needed")
        return

    pids = [int(p) for p in out.stdout.split() if p.strip().isdigit()]
    if not pids:
        print(f"  · No process listening on port {port}")
        return

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"  ✓ Sent SIGTERM to PID {pid} on port {port}")
        except ProcessLookupError:
            pass
        except PermissionError:
            print(f"  WARN: No permission to kill PID {pid} — kill it manually")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tear down the Northstar Payments Command Center demo")
    parser.add_argument("--yes", action="store_true",
                        help="Skip the confirmation prompt")
    parser.add_argument("--keep-db", action="store_true",
                        help="Keep the database; only drop search indexes + free port")
    parser.add_argument("--keep-port", action="store_true",
                        help="Leave the Streamlit process running")
    parser.add_argument("--clear-zone-ranges", action="store_true",
                        help="Remove the per-region zone key ranges (useful with --keep-db)")
    parser.add_argument("--port", type=int, default=_default_port(),
                        help="Streamlit port to free (default: STREAMLIT_SERVER_PORT or 8501)")
    args = parser.parse_args()

    name = db_name()
    print("This will:")
    print("  - drop any Atlas Search indexes on the demo collections")
    if args.clear_zone_ranges:
        print("  - clear the per-region zone key ranges")
    if not args.keep_db:
        print(f"  - drop the Atlas database '{name}' (all demo collections)")
    if not args.keep_port:
        print(f"  - free the Streamlit port {args.port}")

    if not args.yes:
        answer = input("Proceed? [y/N]: ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return

    print("\nTearing down...")
    drop_search_indexes()
    if args.clear_zone_ranges:
        clear_zone_ranges()
    if not args.keep_db:
        drop_demo_database()
    else:
        print("  · Keeping database (per --keep-db)")
    if not args.keep_port:
        free_port(args.port)
    else:
        print("  · Leaving Streamlit running (per --keep-port)")

    get_client().close()
    print("\nTeardown complete.")


if __name__ == "__main__":
    main()
