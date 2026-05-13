"""Seed data for the sharding demo.

Inserts ~100,000 synthetic event documents with three fields useful for
demonstrating each sharding strategy:

  customer_id : int      (uniform random — good hashed-shard-key target)
  created_at  : datetime (monotonically increasing — classic ranged anti-pattern)
  location    : "EU"|"US" (categorical — drives zone-based routing)

Re-running is safe: the script drops and rebuilds the collection so a fresh
demo always starts from the same baseline.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


TOTAL_DOCS = 100_000
BATCH_SIZE = 5_000
COLLECTION = "events"


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    uri = require_env("SHARDED_URI")
    db_name = os.getenv("DEMO_DB", "architecture_demo")

    client = MongoClient(uri, retryWrites=True, w="majority")
    db = client[db_name]
    coll = db[COLLECTION]

    print(f"Seeding {db_name}.{COLLECTION} on the sharded cluster")
    print(f"  Target documents : {TOTAL_DOCS:,}")
    print(f"  Batch size       : {BATCH_SIZE:,}\n")

    coll.drop()

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rng = random.Random(42)

    inserted = 0
    while inserted < TOTAL_DOCS:
        batch = []
        for i in range(min(BATCH_SIZE, TOTAL_DOCS - inserted)):
            seq = inserted + i
            batch.append(
                {
                    "_id": seq,
                    "customer_id": rng.randint(1, 50_000),
                    "created_at": start + timedelta(seconds=seq),
                    "location": "EU" if rng.random() < 0.5 else "US",
                    "amount": round(rng.uniform(1, 1000), 2),
                }
            )
        coll.insert_many(batch, ordered=False)
        inserted += len(batch)
        print(f"  inserted {inserted:>7,} / {TOTAL_DOCS:,}")

    print(f"\nDone. {coll.estimated_document_count():,} documents in {db_name}.{COLLECTION}.")
    print("Next: open mongosh and run 03-sharding/01_hashed.js (or 02/03).")

    client.close()


if __name__ == "__main__":
    main()
