"""
Seeds a small e-commerce workload into MongoDB Atlas.

This represents the *operational* tier — the data your live application reads
and writes. The shape is deliberately document-oriented: orders embed their
line items, customers embed their addresses. Nothing here is warehouse-first.

Run once. Re-running drops and re-seeds the demo database so the dataset is
reproducible across runs.
"""

import os
import random
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient

load_dotenv()

MONGODB_URI = os.environ["MONGODB_URI"]
DB_NAME     = os.environ.get("DB_NAME", "atlas_databricks_demo")
NUM_ORDERS  = int(os.environ.get("NUM_ORDERS", "250"))

# Deterministic data so reruns and screenshots match across machines
random.seed(42)

CATEGORIES = ["electronics", "apparel", "home", "outdoors", "books"]
REGIONS    = ["us-east", "us-west", "us-central", "eu-west", "ap-southeast"]
TIERS      = ["standard", "premium", "platinum"]
STATUSES   = ["pending", "shipped", "delivered", "cancelled"]
EVENT_TYPES = ["page_view", "add_to_cart", "checkout_start", "purchase"]


def build_products(n: int = 30) -> list[dict]:
    products = []
    for i in range(1, n + 1):
        category = random.choice(CATEGORIES)
        # Flexible schema: attributes vary by category — a relational warehouse
        # would force this into nullable columns; documents just carry the
        # fields that apply.
        if category == "apparel":
            attrs = {"size": random.choice(["S", "M", "L", "XL"]),
                     "color": random.choice(["black", "white", "navy", "olive"])}
        elif category == "electronics":
            attrs = {"warrantyMonths": random.choice([12, 24, 36]),
                     "voltage": random.choice(["110V", "220V", "dual"])}
        else:
            attrs = {"weightKg": round(random.uniform(0.2, 5.0), 2)}
        products.append({
            "sku": f"P-{100 + i}",
            "name": f"{category.title()} Item {i}",
            "category": category,
            "price": round(random.uniform(9.99, 499.99), 2),
            "stock": random.randint(0, 500),
            "attributes": attrs,
        })
    return products


def build_customers(n: int = 60) -> list[dict]:
    customers = []
    now = datetime.now(timezone.utc)
    for i in range(1, n + 1):
        signup_days_ago = random.randint(1, 540)
        customers.append({
            "customerId": f"C-{1000 + i}",
            "email": f"customer{i}@example.com",
            "name": f"Customer {i}",
            "tier": random.choices(TIERS, weights=[60, 30, 10])[0],
            "region": random.choice(REGIONS),
            # Embedded addresses — one document, no join
            "addresses": [{
                "type": "shipping",
                "city": random.choice(["Austin", "Seattle", "London", "Singapore", "Berlin"]),
                "country": random.choice(["US", "UK", "SG", "DE"]),
            }],
            "createdAt": now - timedelta(days=signup_days_ago),
            "lastLogin": now - timedelta(days=random.randint(0, 30)),
        })
    return customers


def build_orders(customers: list[dict], products: list[dict]) -> list[dict]:
    orders = []
    now = datetime.now(timezone.utc)
    for i in range(1, NUM_ORDERS + 1):
        customer = random.choice(customers)
        line_count = random.randint(1, 4)
        items = []
        for _ in range(line_count):
            p = random.choice(products)
            qty = random.randint(1, 3)
            items.append({
                "sku": p["sku"],
                "name": p["name"],
                "category": p["category"],
                "qty": qty,
                "unitPrice": p["price"],
                "lineTotal": round(p["price"] * qty, 2),
            })
        subtotal = round(sum(it["lineTotal"] for it in items), 2)
        orders.append({
            "orderId": f"O-{i:06d}",
            "customerId": customer["customerId"],
            "region": customer["region"],
            "status": random.choices(STATUSES, weights=[10, 20, 65, 5])[0],
            "items": items,                    # embedded — no join at read time
            "subtotal": subtotal,
            "tax": round(subtotal * 0.08, 2),
            "total": round(subtotal * 1.08, 2),
            "placedAt": now - timedelta(days=random.randint(0, 180),
                                        hours=random.randint(0, 23)),
        })
    return orders


def build_events(customers: list[dict], products: list[dict], n: int = 1500) -> list[dict]:
    events = []
    now = datetime.now(timezone.utc)
    for i in range(n):
        customer = random.choice(customers)
        events.append({
            "eventId": f"E-{i:07d}",
            "customerId": customer["customerId"],
            "eventType": random.choices(EVENT_TYPES, weights=[60, 20, 12, 8])[0],
            "productSku": random.choice(products)["sku"],
            "sessionId": f"S-{random.randint(1, 400)}",
            "ts": now - timedelta(minutes=random.randint(0, 60 * 24 * 30)),
        })
    return events


def main():
    print(f"Connecting to Atlas, target database: {DB_NAME}")
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)
    db = client[DB_NAME]

    print("Dropping existing demo collections (idempotent re-seed)...")
    for name in ("customers", "products", "orders", "events"):
        db[name].drop()

    products  = build_products()
    customers = build_customers()
    orders    = build_orders(customers, products)
    events    = build_events(customers, products)

    print(f"Inserting {len(products)} products, {len(customers)} customers, "
          f"{len(orders)} orders, {len(events)} events...")
    db.products.insert_many(products)
    db.customers.insert_many(customers)
    db.orders.insert_many(orders)
    db.events.insert_many(events)

    # Indexes that match the operational query patterns in operational_queries.py
    db.customers.create_index([("customerId", ASCENDING)], unique=True)
    db.products.create_index([("sku", ASCENDING)], unique=True)
    db.orders.create_index([("customerId", ASCENDING), ("placedAt", ASCENDING)])
    db.events.create_index([("customerId", ASCENDING), ("ts", ASCENDING)])

    print("Seed complete.")
    print(f"  Database: {DB_NAME}")
    print(f"  Run: python3 operational_queries.py   (app-side patterns)")
    print(f"  Run: python3 export_to_s3.py          (handoff to analytics tier)")
    client.close()


if __name__ == "__main__":
    main()
