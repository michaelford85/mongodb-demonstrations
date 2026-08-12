"""Seed a minimal orders dataset so reads have something to find on a cold run.

    python app/seed.py                 insert 500 synthetic orders
    python app/seed.py --count 5000    a larger baseline
    python app/seed.py --drop          drop the collection first
    python app/seed.py --clean         drop and exit

The service works without this — the generator writes as it goes — but seeding
first means the read path is exercised from the very first tick.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: E402
from pymongo import ASCENDING  # noqa: E402
from workload import make_order  # noqa: E402

BATCH_SIZE = 500


def seed(count: int, drop: bool) -> None:
    orders = config.get_orders()
    if drop:
        orders.drop()
        print(f"Dropped {config.DB_NAME}.{config.ORDERS_COLLECTION}")

    inserted = 0
    while inserted < count:
        batch = [make_order() for _ in range(min(BATCH_SIZE, count - inserted))]
        orders.insert_many(batch)
        inserted += len(batch)

    orders.create_index([("order_id", ASCENDING)], name="order_id_1")
    orders.create_index([("region", ASCENDING), ("created_at", ASCENDING)],
                        name="region_created_at")

    print(f"Inserted {inserted} orders into "
          f"{config.DB_NAME}.{config.ORDERS_COLLECTION}")
    print("Indexes: order_id_1, region_created_at")
    print(f"Collection now holds {orders.estimated_document_count()} documents")


def clean() -> None:
    config.get_orders().drop()
    print(f"Dropped {config.DB_NAME}.{config.ORDERS_COLLECTION}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed or clean the resilience lab orders collection."
    )
    parser.add_argument("--count", type=int, default=500,
                        help="documents to insert (default: 500)")
    parser.add_argument("--drop", action="store_true",
                        help="drop the collection before seeding")
    parser.add_argument("--clean", action="store_true",
                        help="drop the collection and exit")
    args = parser.parse_args()

    try:
        if args.clean:
            clean()
        else:
            seed(args.count, args.drop)
    except RuntimeError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
