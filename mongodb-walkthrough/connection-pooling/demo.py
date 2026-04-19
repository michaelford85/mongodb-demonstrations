"""
Benchmarks three connection patterns against sample_mflix.movies:

  Pattern 1 — No pool   : new MongoClient created and closed per operation (anti-pattern)
  Pattern 2 — Pooled    : single MongoClient, operations run sequentially
  Pattern 3 — Concurrent: single MongoClient, operations run across a thread pool

The comparison makes the overhead of connection establishment visible.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("DB_NAME", "sample_mflix")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "movies")
N = int(os.environ.get("NUM_OPERATIONS", "50"))

# Spread queries across 50 different years so results are not all cached identically
YEARS = [1960 + (i % 50) for i in range(N)]


def divider(title):
    print(f"\n{'─'*62}")
    print(f"  {title}")
    print(f"{'─'*62}")


def fetch_new_client(year):
    """Anti-pattern: creates a brand-new MongoClient (and TCP+TLS handshake) per call."""
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)
    result = client[DB_NAME][COLLECTION_NAME].find_one({"year": year}, {"title": 1})
    client.close()
    return result


def fetch_pooled(collection, year):
    """Correct pattern: reuses an existing connection from the pool."""
    return collection.find_one({"year": year}, {"title": 1})


def main():
    print("=== MongoDB Connection Pooling Demo ===")
    print(f"Workload : {N} find_one queries  |  {DB_NAME}.{COLLECTION_NAME}")

    results = {}

    # ── Pattern 1: new client per operation ────────────────────────
    divider(f"Pattern 1 — New MongoClient per operation  (anti-pattern)")
    print("  Each query opens a new TCP connection, performs a TLS handshake,")
    print("  authenticates, runs the query, then closes the connection.")
    print(f"  Running {N} queries...")
    start = time.time()
    for year in YEARS:
        fetch_new_client(year)
    results["no_pool"] = time.time() - start
    print(f"  Done.  Total: {results['no_pool']:.2f}s   Per op: {results['no_pool']/N*1000:.0f}ms")

    # ── Pattern 2: shared pool, sequential ─────────────────────────
    divider("Pattern 2 — Shared MongoClient pool, sequential")
    print("  One client is created at startup. Connections are checked out")
    print("  from the pool and returned after each operation.")
    print(f"  Running {N} queries...")
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)
    coll = client[DB_NAME][COLLECTION_NAME]
    coll.find_one({})  # warm the pool before timing

    start = time.time()
    for year in YEARS:
        fetch_pooled(coll, year)
    results["pool_seq"] = time.time() - start
    print(f"  Done.  Total: {results['pool_seq']:.2f}s   Per op: {results['pool_seq']/N*1000:.0f}ms")

    # ── Pattern 3: shared pool, concurrent ─────────────────────────
    divider("Pattern 3 — Shared MongoClient pool, concurrent  (threads)")
    print("  Same single client as Pattern 2. Operations are dispatched")
    print("  concurrently across a thread pool — the driver handles connection")
    print("  checkout and return automatically across threads.")
    print(f"  Running {N} queries across 10 threads...")
    start = time.time()
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_pooled, coll, year) for year in YEARS]
        for f in as_completed(futures):
            f.result()
    results["pool_concurrent"] = time.time() - start
    print(f"  Done.  Total: {results['pool_concurrent']:.2f}s   Per op: {results['pool_concurrent']/N*1000:.0f}ms")

    client.close()

    # ── Summary ─────────────────────────────────────────────────────
    divider("Summary")
    col = 42
    print(f"  {'Pattern':<{col}} {'Total':>7}  {'Per op':>7}")
    print(f"  {'─'*col} {'─'*7}  {'─'*7}")
    print(f"  {'New client per operation (no pool)':<{col}} {results['no_pool']:>6.2f}s  {results['no_pool']/N*1000:>5.0f}ms")
    print(f"  {'Shared pool — sequential':<{col}} {results['pool_seq']:>6.2f}s  {results['pool_seq']/N*1000:>5.0f}ms")
    print(f"  {'Shared pool — concurrent (10 threads)':<{col}} {results['pool_concurrent']:>6.2f}s  {results['pool_concurrent']/N*1000:>5.0f}ms")
    print()

    speedup = results["no_pool"] / results["pool_seq"]
    print(f"  Pool reuse is ~{speedup:.1f}x faster than creating a new connection each time.")
    print()
    print("  Key takeaways:")
    print("  · Create MongoClient once at application startup; reuse it for the")
    print("    lifetime of the process. It is designed to be shared across threads.")
    print("  · In a multi-tenant deployment, a single client handles all tenant")
    print("    databases — client[tenant_a_db] and client[tenant_b_db] both draw")
    print("    from the same underlying connection pool.")
    print("  · Default pool size is 100 connections. Tune maxPoolSize to match")
    print("    your application's concurrency profile.")


if __name__ == "__main__":
    main()
