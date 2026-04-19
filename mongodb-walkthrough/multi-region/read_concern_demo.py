"""
Demonstrates MongoDB read concern levels and their consistency guarantees.

Read concern controls which version of data a query can return:

  local        — data on the local node's in-memory state; may include writes
                 that have not yet been replicated to a majority of nodes
  majority     — data that a majority of nodes have acknowledged; safe across
                 failovers and region outages
  linearizable — all previous majority-acknowledged writes are visible; strongest
                 guarantee, primary only, higher latency
  available    — fastest; may return data that is rolled back on a failover
                 (mostly relevant for sharded clusters, shown here for completeness)

The demo writes a document with w="majority", then reads it back at each concern
level and times the response. It also shows that linearizable is only valid
against the primary by attempting it with a Secondary read preference.
"""

import os
import time
import datetime
from pymongo import MongoClient, ReadPreference
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern
from pymongo.errors import OperationFailure, NotPrimaryError
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("DB_NAME", "sample_mflix")
TEST_COLLECTION = "_demo_read_concern"

CONCERNS = [
    (
        "available",
        ReadConcern("available"),
        ReadPreference.PRIMARY,
        "Returns data from the node's local state with no replication check.\n"
        "    Fastest of all levels. May return data later rolled back (rare on\n"
        "    replica sets, more relevant on sharded clusters).",
    ),
    (
        "local",
        ReadConcern("local"),
        ReadPreference.PRIMARY,
        "Returns data present on the queried node. Does not guarantee the data\n"
        "    has been replicated to a majority. Default for most read operations.",
    ),
    (
        "majority",
        ReadConcern("majority"),
        ReadPreference.PRIMARY,
        "Only returns data acknowledged by a majority of replica set nodes.\n"
        "    Safe across failovers — data at this level will never be rolled back.",
    ),
    (
        "linearizable",
        ReadConcern("linearizable"),
        ReadPreference.PRIMARY,
        "Strongest guarantee: reflects all majority-acknowledged writes that\n"
        "    completed before the read started. Primary only. Higher latency\n"
        "    because it may wait for in-flight replication to settle.",
    ),
]


def divider(title):
    print(f"\n{'─'*62}")
    print(f"  {title}")
    print(f"{'─'*62}")


def main():
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)
    db = client[DB_NAME]

    # Warm the connection pool so topology is discovered before benchmarking.
    client.admin.command("ping")

    print("=== Read Concern Demo ===")
    print(f"Primary  : {client.primary}")

    # ── Write a known document to read back ─────────────────────────
    divider("Setup — writing a test document with w='majority'")
    write_coll = db[TEST_COLLECTION].with_options(
        write_concern=WriteConcern(w="majority")
    )
    doc = {"demo": "read_concern", "ts": datetime.datetime.now(datetime.UTC)}
    result = write_coll.insert_one(doc)
    doc_id = result.inserted_id
    print(f"  Inserted document _id={doc_id}")
    print(f"  This document is confirmed on a majority of nodes before we read it.")

    # ── Read it back at each concern level ───────────────────────────
    timings = []

    for level, rc, rp, explanation in CONCERNS:
        divider(f"Read concern: {level}")
        print(f"  {explanation}\n")

        coll = db[TEST_COLLECTION].with_options(
            read_concern=rc,
            read_preference=rp,
        )

        try:
            start = time.time()
            found = coll.find_one({"_id": doc_id})
            elapsed_ms = (time.time() - start) * 1000

            if found:
                print(f"  Document found  ✓")
            else:
                print(f"  Document NOT found at this concern level.")

            print(f"  Latency : {elapsed_ms:.1f}ms")
            timings.append((level, True, elapsed_ms))

        except OperationFailure as e:
            print(f"  OperationFailure: {e}")
            timings.append((level, False, None))

    # ── Show that linearizable fails on a secondary ──────────────────
    divider("Verification: linearizable is rejected on a secondary")
    try:
        coll_sec = db[TEST_COLLECTION].with_options(
            read_concern=ReadConcern("linearizable"),
            read_preference=ReadPreference.SECONDARY,
        )
        list(coll_sec.find({"_id": doc_id}))
        print("  No error raised — cluster may have routed back to primary.")
    except (OperationFailure, NotPrimaryError) as e:
        print(f"  {type(e).__name__} raised as expected:")
        print(f"  {e.details.get('errmsg', str(e))}")
        print()
        print("  This confirms linearizable enforces primary-only reads.")

    # ── Summary ─────────────────────────────────────────────────────
    divider("Summary")
    col = 16
    print(f"  {'Concern':<{col}} {'Found':>6}  {'Latency':>9}  Notes")
    print(f"  {'─'*col} {'─'*6}  {'─'*9}  {'─'*30}")
    notes = {
        "available":    "fastest; no replication guarantee",
        "local":        "default; node-local state",
        "majority":     "safe across failover",
        "linearizable": "strongest; primary only",
    }
    for level, found, ms in timings:
        ms_str = f"{ms:.1f}ms" if ms is not None else "—"
        print(f"  {level:<{col}} {str(found):>6}  {ms_str:>9}  {notes.get(level, '')}")

    print()
    print("  Latency typically increases from available → local → majority → linearizable.")
    print("  The difference is most visible under write load and on multi-region clusters")
    print("  where majority acknowledgment involves cross-region replication.")

    # ── Cleanup ─────────────────────────────────────────────────────
    divider("Cleanup")
    db[TEST_COLLECTION].drop()
    print(f"  Dropped temporary collection '{TEST_COLLECTION}'.")

    client.close()


if __name__ == "__main__":
    main()
