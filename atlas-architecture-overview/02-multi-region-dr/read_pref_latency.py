"""Compare read latency across read preferences.

Runs the same trivial query (count of a small seed collection) repeatedly
under three read preferences and reports min/median/max round-trip times.

Headline finding:
  - `primary`            : always hits the primary, wherever it is
  - `secondaryPreferred` : hits the nearest secondary that's caught up
  - `nearest`            : hits the lowest-latency member, primary or not

On a 3-region cluster, from a client co-located with a secondary, `nearest`
typically wins by 50-150 ms.
"""

from __future__ import annotations

import os
import statistics
import time
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.read_preferences import (
    Nearest,
    Primary,
    SecondaryPreferred,
)


ITERATIONS = 30
COLLECTION = "dr_latency_probe"


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def ensure_seed(client: MongoClient, db_name: str) -> None:
    coll = client[db_name][COLLECTION]
    if coll.estimated_document_count() == 0:
        coll.insert_many([{"_id": i, "value": i * i} for i in range(100)])


def time_reads(client: MongoClient, db_name: str, read_pref) -> list[float]:
    coll = client[db_name].get_collection(COLLECTION, read_preference=read_pref)
    samples = []
    for _ in range(ITERATIONS):
        started = time.monotonic()
        coll.find_one({"_id": 42})
        samples.append((time.monotonic() - started) * 1000)
    return samples


def summarise(label: str, samples: list[float]) -> None:
    print(
        f"  {label:<22} "
        f"min={min(samples):6.1f} ms  "
        f"p50={statistics.median(samples):6.1f} ms  "
        f"max={max(samples):6.1f} ms"
    )


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    uri = require_env("REPLICASET_URI")
    db_name = os.getenv("DEMO_DB", "architecture_demo")

    # A fresh client per read preference avoids server-selection caching.
    seeder = MongoClient(uri)
    ensure_seed(seeder, db_name)
    seeder.close()

    print(f"\nRead-preference latency probe ({ITERATIONS} iterations each)")
    print(f"Database/collection : {db_name}.{COLLECTION}\n")

    for label, pref in [
        ("primary", Primary()),
        ("secondaryPreferred", SecondaryPreferred()),
        ("nearest", Nearest()),
    ]:
        client = MongoClient(uri, read_preference=pref)
        samples = time_reads(client, db_name, pref)
        summarise(label, samples)
        client.close()

    print()


if __name__ == "__main__":
    main()
