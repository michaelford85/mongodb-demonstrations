"""Primary-watcher for the RPO/RTO demo.

Polls the cluster's hello() command every second and reprints a single status
line whenever the primary host changes. Pair this with writer.py and the Atlas
UI's "Test Primary Failover" button to demonstrate RTO live.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def hello(client: MongoClient) -> dict:
    return client.admin.command("hello")


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    uri = require_env("REPLICASET_URI")
    client = MongoClient(uri)

    print("Watcher connected. Polling hello() every 1 s.")
    print("Each line prints when the primary changes (or every 30 s as a heartbeat).")
    print("Stop with Ctrl+C.\n")

    def handle_sigint(_sig, _frame):
        print("\nWatcher stopped.")
        client.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    last_primary: str | None = None
    last_print = 0.0
    last_change: datetime | None = None

    while True:
        now = time.monotonic()
        try:
            info = hello(client)
            primary = info.get("primary") or "(none — election in progress)"
            set_name = info.get("setName", "?")
            hosts = info.get("hosts", [])

            changed = primary != last_primary
            heartbeat = now - last_print > 30

            if changed or heartbeat:
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                tag = "CHANGE " if changed else "       "
                if changed:
                    last_change = datetime.now(timezone.utc)
                print(
                    f"  {ts}  {tag}  set={set_name}  primary={primary}  "
                    f"members={len(hosts)}"
                )
                last_primary = primary
                last_print = now
        except PyMongoError as exc:
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            print(f"  {ts}  ERROR   {type(exc).__name__}: {exc}")
            last_print = now

        time.sleep(1.0)


if __name__ == "__main__":
    main()
