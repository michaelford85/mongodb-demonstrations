"""Seed a modest historical securities-order dataset into MongoDB Atlas.

Deterministic (random.seed(42)) so every run and screenshot matches. Re-running
drops and re-seeds the demo collection — it never touches any other namespace.
No real customer data or PII: synthetic accounts and public ticker symbols only.
"""

import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

log = common.get_logger("seed")

SYMBOLS = ["MDB", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "TSLA", "JPM"]
BASE_PRICE = {"MDB": 355.0, "AAPL": 225.0, "MSFT": 430.0, "NVDA": 135.0,
              "AMZN": 205.0, "GOOGL": 190.0, "TSLA": 250.0, "JPM": 245.0}
SIDES = ["BUY", "SELL"]
STATUSES = ["NEW", "PARTIALLY_FILLED", "FILLED", "CANCELLED"]


def build_orders(n: int) -> list[dict]:
    random.seed(42)
    now = datetime.now(timezone.utc)
    orders = []
    for i in range(1, n + 1):
        symbol = random.choice(SYMBOLS)
        price = round(BASE_PRICE[symbol] * random.uniform(0.95, 1.05), 2)
        placed = now - timedelta(days=random.randint(1, 30),
                                 minutes=random.randint(0, 1439))
        orders.append({
            "order_id": f"O-{i:06d}",
            "account_id": f"ACCT-{random.randint(1000, 1099)}",
            "symbol": symbol,
            "side": random.choice(SIDES),
            "quantity": random.randint(1, 500),
            "price": price,
            "order_time": placed,
            "order_status": random.choices(STATUSES, weights=[10, 15, 70, 5])[0],
            "source_updated_at": placed,
        })
    return orders


def main() -> None:
    common.banner("SEED · historical orders → Atlas")
    client = common.get_mongo_client()
    try:
        if not common.supports_change_streams(client):
            log.error("Target deployment does not support change streams "
                      "(not a replica set / sharded cluster).")
            sys.exit(1)

        coll = common.get_collection(client)
        log.info("Dropping existing collection %s.%s (idempotent re-seed)",
                 common.DB_NAME, common.COLLECTION_NAME)
        coll.drop()

        orders = build_orders(common.SEED_ORDER_COUNT)
        coll.insert_many(orders)
        coll.create_index("order_id", unique=True)

        log.info("Inserted %d historical orders into %s.%s",
                 len(orders), common.DB_NAME, common.COLLECTION_NAME)
        log.info("Next: make backfill")
    finally:
        client.close()


if __name__ == "__main__":
    main()
