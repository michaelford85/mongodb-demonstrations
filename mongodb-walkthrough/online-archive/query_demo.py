"""
Demonstrates query response times against live (hot) vs. archived (cold) data.

  MONGODB_URI   — cluster connection string, queries live data only
  FEDERATED_URI — Atlas Data Federation endpoint, queries live + archived data

Run setup_archive.py first and allow time for the archive to process.
"""

import os
import time
import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.environ["MONGODB_URI"]
FEDERATED_URI = os.environ.get("FEDERATED_URI", "")
DB_NAME = os.environ.get("DB_NAME", "sample_mflix")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "movies")
EXPIRE_AFTER_DAYS = int(os.environ.get("ARCHIVE_EXPIRE_AFTER_DAYS", "9000"))

cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=EXPIRE_AFTER_DAYS)
cutoff_year = cutoff_date.year


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
    print(f"{'='*62}")

    client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
    coll = client[DB_NAME][COLLECTION_NAME]

    print()
    timed_query(
        coll,
        {"released": {"$gte": datetime.datetime(cutoff_year, 1, 1)}},
        f"Recent data  (released on or after {cutoff_year})",
    )
    timed_query(
        coll,
        {"released": {"$lt": datetime.datetime(cutoff_year, 1, 1)}},
        f"Older data   (released before {cutoff_year}  ← archived tier)",
    )
    timed_query(coll, {}, "Full scan    (all documents, both tiers)")

    client.close()


def main():
    print("=== Atlas Online Archive — Query Tier Demo ===")
    print(f"Archive cutoff  : ~{cutoff_year}  ({EXPIRE_AFTER_DAYS} days ago)")
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
        print("Add FEDERATED_URI to .env once archiving has completed and a Data")
        print("Federation endpoint appears in Atlas UI → Data Federation.")


if __name__ == "__main__":
    main()
