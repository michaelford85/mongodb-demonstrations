"""Tear down the CropTrace demo.

Drops the demo's Atlas Vector Search index, drops the demo database (all demo
collections), and frees the local Streamlit port. Only touches this demo's
database — no other database on the cluster is affected.

    python3 teardown.py                  # prompts, then tears everything down
    python3 teardown.py --yes            # no prompt
    python3 teardown.py --keep-db        # only drop index + free the port
    python3 teardown.py --port 8502      # override the Streamlit port to free
"""

import argparse
import os
import signal
import subprocess

from pymongo.errors import OperationFailure, PyMongoError

from lib.atlas_client import (COLLECTIONS, KNOWLEDGE_COLLECTION, db_name,
                              get_client, get_db)
from lib.queries import VECTOR_INDEX


def _default_port() -> int:
    return int(os.getenv("STREAMLIT_SERVER_PORT", "8501"))


def drop_search_index() -> None:
    coll = get_db()[KNOWLEDGE_COLLECTION]
    try:
        existing = {idx["name"] for idx in coll.list_search_indexes()}
    except PyMongoError:
        existing = set()
    if VECTOR_INDEX not in existing:
        print(f"  · Search index '{VECTOR_INDEX}' not present — skipping")
        return
    try:
        coll.drop_search_index(VECTOR_INDEX)
        print(f"  ✓ Dropped search index '{VECTOR_INDEX}'")
    except OperationFailure as e:
        print(f"  WARN: Could not drop search index '{VECTOR_INDEX}': {e}")


def drop_demo_database() -> None:
    client = get_client()
    name = db_name()
    client.drop_database(name)
    print(f"  ✓ Dropped database '{name}' ({len(COLLECTIONS)} demo collections)")


def free_port(port: int) -> None:
    try:
        out = subprocess.run(["lsof", "-ti", f"tcp:{port}"],
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
    parser = argparse.ArgumentParser(description="Tear down the CropTrace demo")
    parser.add_argument("--yes", action="store_true",
                        help="Skip the confirmation prompt")
    parser.add_argument("--keep-db", action="store_true",
                        help="Keep the database; only drop index + free port")
    parser.add_argument("--keep-port", action="store_true",
                        help="Leave the Streamlit process running")
    parser.add_argument("--port", type=int, default=_default_port(),
                        help="Streamlit port to free (default: 8501)")
    args = parser.parse_args()

    name = db_name()
    print("This will:")
    print(f"  - drop search index '{VECTOR_INDEX}'")
    if not args.keep_db:
        print(f"  - drop the Atlas database '{name}' (all demo collections)")
    if not args.keep_port:
        print(f"  - free the Streamlit port {args.port}")

    if not args.yes:
        if input("Proceed? [y/N]: ").strip().lower() != "y":
            print("Aborted.")
            return

    print("\nTearing down...")
    drop_search_index()
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
