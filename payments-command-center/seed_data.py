"""Seed Northstar Payments demo data into MongoDB Atlas.

Creates accounts, payment instruments, merchants, then backfills a few minutes
of authorization history so the dashboard looks alive the moment you open it.
Re-running drops and re-seeds the demo database for reproducible runs.

    python3 seed_data.py                 # default sizes
    python3 seed_data.py --accounts 60 --history 400
"""

import argparse
import random
from datetime import datetime, timedelta, timezone

from pymongo import ASCENDING, DESCENDING

from lib.atlas_client import COLLECTIONS, db_name, get_db
from lib.sample_data import build_accounts, build_instruments, build_merchants
from lib.simulator import generate_event, take_snapshot
from scripts.shard_collections import shard_all


def _create_indexes(db) -> None:
    """Indexes aligned to the query patterns in lib/queries.py.

    On a sharded collection a unique index must be prefixed by the full shard
    key, so uniqueness is declared on the region-prefixed shard keys. When the
    collection is already sharded these calls match the index shardCollection
    built and are no-ops; on a plain replica set they still hold.
    """
    db.accounts.create_index([("region", ASCENDING), ("account_id", ASCENDING)],
                             unique=True)
    db.payment_instruments.create_index(
        [("region", ASCENDING), ("account_id", ASCENDING)])
    db.payment_instruments.create_index([("account_id", ASCENDING)])
    db.merchants.create_index([("merchant_id", ASCENDING)], unique=True)
    # Exactly-once: one auth_request per (region, idempotency_key).
    db.auth_requests.create_index(
        [("region", ASCENDING), ("idempotency_key", ASCENDING)], unique=True)
    db.auth_requests.create_index([("request_id", ASCENDING)])
    # Feed + explorer read patterns; one decision per (region, request_id).
    db.auth_decisions.create_index(
        [("region", ASCENDING), ("request_id", ASCENDING)], unique=True)
    db.auth_decisions.create_index([("decided_at", DESCENDING)])
    db.auth_decisions.create_index([("region", ASCENDING), ("decided_at", DESCENDING)])
    db.auth_decisions.create_index([("account_id", ASCENDING), ("decided_at", DESCENDING)])
    db.ledger_events.create_index([("region", ASCENDING), ("event_id", ASCENDING)])
    db.ledger_events.create_index([("account_id", ASCENDING), ("created_at", DESCENDING)])
    db.balance_snapshots.create_index([("region", ASCENDING), ("account_id", ASCENDING)])
    db.balance_snapshots.create_index([("account_id", ASCENDING), ("snapshot_at", DESCENDING)])


def _backfill_history(db, count: int) -> None:
    """Generate `count` past authorizations spread over the last ~15 minutes."""
    now = datetime.now(timezone.utc)
    for i in range(count):
        # Spread events backwards so the throughput chart has recent shape.
        offset = timedelta(seconds=random.randint(0, 15 * 60))
        generate_event(db, at=now - offset)


def seed(accounts: int, history: int) -> None:
    db = get_db()
    print(f"Connecting to Atlas, target database: {db_name()}")

    print("Dropping existing demo collections (idempotent re-seed)...")
    for name in COLLECTIONS:
        db[name].drop()

    # Shard the now-empty collections into per-region zones BEFORE any inserts,
    # so every document routes to its home region's shard. No-op on a plain
    # replica set (the demo expects a GEOSHARDED cluster — see .env.example).
    print("Establishing sharded topology...")
    shard_all(verbose=True)

    _create_indexes(db)

    accts = build_accounts(accounts)
    instruments = build_instruments(accts)
    merchants = build_merchants()

    print(f"Inserting {len(accts)} accounts, {len(instruments)} instruments, "
          f"{len(merchants)} merchants...")
    db.accounts.insert_many(accts)
    db.payment_instruments.insert_many(instruments)
    db.merchants.insert_many(merchants)

    print(f"Backfilling {history} authorization events...")
    _backfill_history(db, history)

    snaps = take_snapshot(db)
    print(f"Wrote {snaps} balance snapshots.")

    print("Seed complete.")
    print(f"  Database : {db_name()}")
    print("  Next     : streamlit run app.py")
    print("  Live data: python3 simulate_payments.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Northstar Payments demo data")
    parser.add_argument("--accounts", type=int, default=40,
                        help="Number of synthetic accounts (default: 40)")
    parser.add_argument("--history", type=int, default=300,
                        help="Number of backfilled authorizations (default: 300)")
    args = parser.parse_args()
    seed(args.accounts, args.history)


if __name__ == "__main__":
    main()
