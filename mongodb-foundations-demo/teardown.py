"""Tear down the demo: drop the demo database and free the Streamlit port.

    python3 teardown.py            # prompts first
    python3 teardown.py --yes      # no prompt
    python3 teardown.py --keep-db  # only free the port

Only `mongodb_foundations_demo` is dropped. No cluster, project, or
Terraform resource is touched.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys

from pymongo.errors import PyMongoError

from lib.mongo_client import DB_NAME, MissingUriError, get_client
from lib.seed import drop_demo_database


def free_port(port: int) -> None:
    try:
        found = subprocess.run(["lsof", "-ti", "tcp:{}".format(port)],
                               capture_output=True, text=True, check=False)
    except FileNotFoundError:
        print("  · 'lsof' unavailable — free port {} manually".format(port))
        return
    pids = [int(p) for p in found.stdout.split() if p.strip().isdigit()]
    if not pids:
        print("  · No process listening on port {}".format(port))
        return
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            print("  ✓ Sent SIGTERM to PID {} on port {}".format(pid, port))
        except (ProcessLookupError, PermissionError):
            print("  WARN: could not stop PID {} — stop it manually".format(pid))


def main() -> int:
    parser = argparse.ArgumentParser(description="Tear down the demo")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    parser.add_argument("--keep-db", action="store_true",
                        help="Keep the demo database; only free the port")
    parser.add_argument("--port", type=int, default=8501,
                        help="Streamlit port to free (default 8501)")
    args = parser.parse_args()

    print("This will:")
    if not args.keep_db:
        print("  - drop the database '{}'".format(DB_NAME))
    print("  - free the Streamlit port {}".format(args.port))
    if not args.yes and input("Proceed? [y/N]: ").strip().lower() != "y":
        print("Aborted.")
        return 0

    if not args.keep_db:
        try:
            drop_demo_database()
            print("  ✓ Dropped '{}'".format(DB_NAME))
            get_client().close()
        except MissingUriError as exc:
            print("  WARN: {}".format(exc))
        except PyMongoError as exc:
            print("  WARN: could not drop the database — {}".format(exc))
    free_port(args.port)
    print("\nTeardown complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
