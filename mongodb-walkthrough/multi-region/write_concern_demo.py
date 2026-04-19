"""
Demonstrates how write concern levels affect durability guarantees and write latency.

Four levels are benchmarked:
  w=0           — unacknowledged: fire and forget, no confirmation returned
  w=1           — primary acknowledges: default; secondaries may not have it yet
  w="majority"  — a majority of nodes confirm: cross-region if multi-region cluster
  w="majority" + j=True — majority + journal flush: strongest durability guarantee

In a multi-region cluster w="majority" requires at least one cross-region
acknowledgment, which makes the latency difference between w=1 and w="majority"
much more visible than on a single-region cluster.

Test documents are written to a temporary collection and cleaned up at the end.
"""

import os
import time
import datetime
from pymongo import MongoClient
from pymongo.write_concern import WriteConcern
from pymongo.errors import WriteConcernError
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("DB_NAME", "sample_mflix")
TEST_COLLECTION = "_demo_write_concern"

CONCERNS = [
    (
        "w=0  (unacknowledged)",
        WriteConcern(w=0),
        "Fire and forget. The driver does not wait for any server response.\n"
        "    Fastest possible write, but silent failures are undetectable.",
    ),
    (
        "w=1  (primary only)",
        WriteConcern(w=1),
        "The primary acknowledges the write. Default behaviour.\n"
        "    Secondaries — including those in remote regions — may not have it yet.",
    ),
    (
        "w='majority'",
        WriteConcern(w="majority"),
        "A majority of replica set nodes confirm the write.\n"
        "    In a multi-region cluster this typically means at least one\n"
        "    cross-region round trip before acknowledgment is returned.",
    ),
    (
        "w='majority' + j=True",
        WriteConcern(w="majority", j=True),
        "Majority acknowledgment AND each confirming node has flushed to its\n"
        "    on-disk journal. Strongest durability guarantee available.",
    ),
]


def divider(title):
    print(f"\n{'─'*62}")
    print(f"  {title}")
    print(f"{'─'*62}")


def main():
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)
    db = client[DB_NAME]

    # Force topology discovery and warm the connection pool before benchmarking.
    # Without this, the first operation pays for DNS resolution, TLS handshake,
    # and authentication — skewing its latency against the other levels.
    client.admin.command("ping")

    print("=== Write Concern Demo ===")
    print(f"Primary    : {client.primary}")
    print(f"Secondaries: {client.secondaries}")

    results = []

    for label, wc, explanation in CONCERNS:
        divider(label)
        print(f"  {explanation}\n")

        coll = db[TEST_COLLECTION].with_options(write_concern=wc)
        doc = {"concern": label, "ts": datetime.datetime.now(datetime.UTC)}

        try:
            start = time.time()
            result = coll.insert_one(doc)
            elapsed_ms = (time.time() - start) * 1000

            print(f"  acknowledged : {result.acknowledged}")
            if result.acknowledged:
                print(f"  inserted_id  : {result.inserted_id}")
            print(f"  latency      : {elapsed_ms:.1f}ms")
            results.append((label, result.acknowledged, elapsed_ms))

        except WriteConcernError as e:
            print(f"  WriteConcernError: {e.details}")
            results.append((label, False, None))

    # ── Summary ─────────────────────────────────────────────────────
    divider("Summary")
    col = 30
    print(f"  {'Level':<{col}} {'Acked':>7}  {'Latency':>9}")
    print(f"  {'─'*col} {'─'*7}  {'─'*9}")
    for label, acked, ms in results:
        ms_str = f"{ms:.1f}ms" if ms is not None else "—"
        print(f"  {label:<{col}} {str(acked):>7}  {ms_str:>9}")

    print()
    print("  Observation: latency increases as the acknowledgment bar rises.")
    print("  On a multi-region cluster the gap between w=1 and w='majority'")
    print("  reflects real cross-region replication time.")

    # ── Cleanup ─────────────────────────────────────────────────────
    divider("Cleanup")
    db[TEST_COLLECTION].drop()
    print(f"  Dropped temporary collection '{TEST_COLLECTION}'.")

    client.close()


if __name__ == "__main__":
    main()
