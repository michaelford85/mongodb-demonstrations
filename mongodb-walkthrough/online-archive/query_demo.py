"""
Demonstrates query response times against live (hot) vs. archived (cold) data.

  MONGODB_URI   — cluster connection string, queries live data only
  FEDERATED_URI — Atlas Data Federation endpoint, queries live + archived data

Queries use the integer 'year' field which exists on every document in
sample_mflix.movies, making the hot/cold split clean and predictable.

Run setup_archive.py first and allow time for the archive to process.
"""

import os
import time
from pymongo import MongoClient
from pymongo.errors import ConfigurationError, ServerSelectionTimeoutError
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI     = os.environ["MONGODB_URI"]
FEDERATED_URI   = os.environ.get("FEDERATED_URI", "")
DB_NAME         = os.environ.get("DB_NAME", "sample_mflix")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "movies")
CUTOFF_YEAR     = int(os.environ.get("ARCHIVE_CUTOFF_YEAR", "2001"))


def timed_query(collection, query, label):
    start = time.time()
    count = collection.count_documents(query)
    elapsed_ms = (time.time() - start) * 1000
    print(f"  {label}")
    print(f"    Filter  : {query}")
    print(f"    Results : {count:,} documents")
    print(f"    Time    : {elapsed_ms:.0f}ms")
    print()
    return elapsed_ms


def run_against(uri, tier_label):
    print(f"\n{'='*62}")
    print(f"  {tier_label}")
    print(f"{'='*62}\n")

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
        coll = client[DB_NAME][COLLECTION_NAME]

        # Sanity check before running timed queries.
        total = coll.estimated_document_count()
        if total == 0:
            print(f"  WARNING: {DB_NAME}.{COLLECTION_NAME} appears empty on this endpoint.")
            print(f"  · Live cluster URI: confirm the sample dataset is loaded.")
            print(f"    Atlas UI → your cluster → ... → Load Sample Dataset")
            print(f"  · Federated URI: the archive may still be initialising.")
            client.close()
            return

        print(f"  Collection total (this endpoint): {total:,} documents\n")

        timed_query(
            coll,
            {"year": {"$gte": CUTOFF_YEAR}},
            f"Recent data  (year >= {CUTOFF_YEAR}  — live tier)",
        )
        timed_query(
            coll,
            {"year": {"$lt": CUTOFF_YEAR}},
            f"Older data   (year <  {CUTOFF_YEAR}  ← archived tier)",
        )
        timed_query(coll, {}, "Full scan    (all documents, both tiers)")

        client.close()

    except ConfigurationError as e:
        print(f"  Connection error: {e}")
        print()
        if "SRV" in str(e) or "DNS" in str(e):
            print("  This is a DNS/SRV lookup failure. Possible causes:")
            print("  · The federated instance is still initialising — wait a few")
            print("    minutes and try again.")
            print("  · Wrong connection string — use 'Connect to Cluster and Online")
            print("    Archive' from Atlas UI → Online Archive → Connect.")
    except ServerSelectionTimeoutError as e:
        print(f"  Could not reach server within timeout: {e}")


def main():
    print("=== Atlas Online Archive — Query Tier Demo ===")
    print(f"Archive cutoff  : year < {CUTOFF_YEAR}")
    print(f"Dataset         : {DB_NAME}.{COLLECTION_NAME}")

    run_against(MONGODB_URI, "LIVE CLUSTER  (hot tier — cluster connection string)")

    if FEDERATED_URI:
        run_against(FEDERATED_URI, "ATLAS DATA FEDERATION  (hot + cold tiers)")
        print("Key observation:")
        print("  Queries that touch only live data perform similarly on both endpoints.")
        print("  Queries against archived data are slower via the federated endpoint,")
        print("  reflecting the cloud-object-storage access pattern (~2–4 s is normal).")
    else:
        print("\n[FEDERATED_URI not set — skipping federated query comparison]")
        print("Add FEDERATED_URI to .env using 'Connect to Cluster and Online Archive'")
        print("from Atlas UI → Online Archive → Connect.")


if __name__ == "__main__":
    main()
