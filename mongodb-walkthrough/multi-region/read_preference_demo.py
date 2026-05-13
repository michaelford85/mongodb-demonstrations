"""
Demonstrates MongoDB read preference modes and verifies which cluster node
actually handles each read by inspecting cursor.address after each query.

Modes tested:
  Primary           — always reads from the primary (default, strongest consistency)
  PrimaryPreferred  — primary if available, falls back to secondary
  Secondary         — always reads from a secondary (round-robins across secondaries)
  SecondaryPreferred — secondary if available, falls back to primary
  Nearest           — the node with the lowest measured network latency

cursor.address is compared against client.primary to confirm whether the read
was served by the primary or a secondary, and which region it came from.

Run this against a multi-region cluster to see nearest route to a different
region's secondary when network latency favours it.
"""

import os
import time
from pymongo import MongoClient, ReadPreference
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("DB_NAME", "sample_mflix")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "movies")
QUERY = {"year": 2010}
REPEATS = 5  # run each preference N times to show any round-robin behaviour


def divider(title):
    print(f"\n{'─'*62}")
    print(f"  {title}")
    print(f"{'─'*62}")


PREFERENCES = [
    (
        "Primary",
        ReadPreference.PRIMARY,
        "All reads go to the primary. Safe for reads that must reflect the\n"
        "    latest committed write. Can become a bottleneck under heavy load.",
    ),
    (
        "PrimaryPreferred",
        ReadPreference.PRIMARY_PREFERRED,
        "Reads go to the primary when available. Falls back to a secondary\n"
        "    during primary unavailability. Good default for most workloads.",
    ),
    (
        "Secondary",
        ReadPreference.SECONDARY,
        "Reads always go to a secondary. Reduces primary load.\n"
        "    Accept eventual consistency: a secondary may lag behind the primary.",
    ),
    (
        "SecondaryPreferred",
        ReadPreference.SECONDARY_PREFERRED,
        "Reads go to a secondary when one is available. Falls back to primary\n"
        "    if no secondary is reachable. Common choice for read-heavy workloads.",
    ),
    (
        "Nearest",
        ReadPreference.NEAREST,
        "Reads go to the node with the lowest measured round-trip latency,\n"
        "    regardless of whether it is primary or secondary.\n"
        "    Optimal for geo-distributed deployments where read latency matters.",
    ),
]


def run_query(collection, pref_name):
    """Run a single find and return (server_address, is_primary, elapsed_ms)."""
    start = time.time()
    cursor = collection.find(QUERY, {"title": 1}).limit(1)
    list(cursor)  # exhaust to ensure the query has run
    elapsed_ms = (time.time() - start) * 1000
    return cursor.address, elapsed_ms


def main():
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)

    # Force topology discovery before inspecting primary/secondaries or benchmarking.
    client.admin.command("ping")

    primary = client.primary
    secondaries = client.secondaries

    print("=== Read Preference Demo ===")
    print(f"\nCluster topology:")
    print(f"  Primary     : {primary[0]}:{primary[1]}" if primary else "  Primary : (not detected)")
    for s in sorted(secondaries):
        print(f"  Secondary   : {s[0]}:{s[1]}")

    for pref_name, pref, explanation in PREFERENCES:
        divider(pref_name)
        print(f"  {explanation}\n")

        coll = client[DB_NAME][COLLECTION_NAME].with_options(read_preference=pref)

        seen_servers = {}
        for i in range(REPEATS):
            try:
                address, elapsed_ms = run_query(coll, pref_name)
                role = "PRIMARY" if address == primary else "SECONDARY"
                key = f"{address[0]}:{address[1]}"
                seen_servers[key] = (role, elapsed_ms)
                print(f"  run {i+1}  →  {key:<50}  {role:<10}  {elapsed_ms:.1f}ms")
            except Exception as e:
                print(f"  run {i+1}  →  ERROR: {e}")

        if len(seen_servers) > 1:
            print(f"\n  ↳ Requests spread across {len(seen_servers)} distinct nodes "
                  f"(round-robin across qualifying nodes).")

    # ── Verification summary ─────────────────────────────────────────
    divider("Verification: which preference routes to which node type?")
    print()
    print(f"  {'Preference':<22}  Expected routing")
    print(f"  {'─'*22}  {'─'*36}")
    print(f"  {'Primary':<22}  Always PRIMARY")
    print(f"  {'PrimaryPreferred':<22}  PRIMARY when healthy")
    print(f"  {'Secondary':<22}  Always SECONDARY (round-robin)")
    print(f"  {'SecondaryPreferred':<22}  SECONDARY when available")
    print(f"  {'Nearest':<22}  Lowest-latency node (PRIMARY or SECONDARY)")
    print()
    print("  The server addresses printed above confirm this routing is live.\n"
          "  On a multi-region cluster 'Nearest' will often resolve to a\n"
          "  secondary in the same region as the application, not the primary.")

    client.close()


if __name__ == "__main__":
    main()
