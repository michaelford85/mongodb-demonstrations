"""Continuous-writer for the RPO/RTO demo.

Inserts a monotonically-numbered document every ~200 ms with w=majority and
retryable writes. When the cluster's primary fails over, PyMongo retries the
write transparently — the output pauses briefly, then the sequence resumes
with the next number (no gaps, no duplicates).
"""

from __future__ import annotations

import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient, WriteConcern
from pymongo.errors import PyMongoError


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    uri = require_env("REPLICASET_URI")
    db_name = os.getenv("DEMO_DB", "architecture_demo")

    # retryWrites is the Atlas default but we set it explicitly for clarity.
    client = MongoClient(uri, retryWrites=True, w="majority")
    coll = client[db_name].get_collection(
        "rpo_rto_events", write_concern=WriteConcern("majority")
    )

    print(f"Writer connected to {db_name}.rpo_rto_events")
    print("Each line below = one majority-acknowledged insert.")
    print("During a failover the line rate will briefly stop, then resume.")
    print("Stop with Ctrl+C.\n")

    seq = 0

    def handle_sigint(_sig, _frame):
        print(f"\nStopped after {seq} successful inserts.")
        client.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    while True:
        seq += 1
        started = time.monotonic()
        try:
            coll.insert_one(
                {
                    "_id": seq,
                    "ts": datetime.now(timezone.utc),
                    "payload": "x" * 64,
                }
            )
            elapsed_ms = (time.monotonic() - started) * 1000
            print(f"  #{seq:>6}  ack in {elapsed_ms:6.1f} ms")
        except PyMongoError as exc:
            elapsed_ms = (time.monotonic() - started) * 1000
            # Retryable writes already retried once internally; a surfaced error
            # here means the second attempt also failed. Keep going — the next
            # iteration may succeed once a new primary is elected.
            print(
                f"  #{seq:>6}  FAILED after {elapsed_ms:6.1f} ms: "
                f"{type(exc).__name__}: {exc}"
            )

        time.sleep(0.2)


if __name__ == "__main__":
    main()
