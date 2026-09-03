"""Load the synthetic orders / customers data into the lab namespace.

The seed data deliberately stores order_id and customer_id as *strings* that
happen to be UUIDs — the shape you inherit from a relational migration or a
JSON API. Both demos build on that: one converts them, the other queries them.
"""
import json
from datetime import datetime, timezone

from config import (
    CUSTOMERS_COLLECTION,
    DATA_DIR,
    DB_NAME,
    ORDERS_COLLECTION,
    ORDER_DATE_INDEX,
    get_customers,
    get_orders,
)

_DATE_FIELDS = {"order_date", "signup_date"}


def _parse_dates(doc: dict) -> dict:
    """Turn ISO-8601 strings into BSON dates so range queries behave."""
    for field in _DATE_FIELDS & doc.keys():
        doc[field] = datetime.fromisoformat(
            doc[field].replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    return doc


def _load(path_name: str) -> list:
    return [_parse_dates(d) for d in json.loads((DATA_DIR / path_name).read_text())]


def seed(drop: bool = False) -> None:
    orders, customers = get_orders(), get_customers()

    if drop:
        orders.drop()
        customers.drop()
        print(f"Dropped {DB_NAME}.{ORDERS_COLLECTION} and "
              f"{DB_NAME}.{CUSTOMERS_COLLECTION}")

    if orders.count_documents({}) or customers.count_documents({}):
        print(f"Data already present in {DB_NAME}. Use --drop to reload.")
        return

    order_docs = _load("orders.json")
    customer_docs = _load("customers.json")
    orders.insert_many(order_docs)
    customers.insert_many(customer_docs)

    # The query-settings demo pins a query shape to this index by name.
    orders.create_index("order_date", name=ORDER_DATE_INDEX)

    print(f"Inserted {len(order_docs)} orders and {len(customer_docs)} customers "
          f"into {DB_NAME}")
    print(f"Created index {ORDER_DATE_INDEX} on {ORDERS_COLLECTION}.order_date")
