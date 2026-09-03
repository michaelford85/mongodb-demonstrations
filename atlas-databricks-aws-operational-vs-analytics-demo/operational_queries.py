"""
Runs the operational query patterns an application would use against Atlas.

These are the kinds of reads and writes the live application performs
hundreds of times per second: single-customer lookups, inventory checks,
order placement, recent-activity feeds. Latency targets are milliseconds,
not seconds — and the data shape is optimised for that.

The same data will be exported to S3 by export_to_s3.py for downstream
analytics in Databricks. The point is not that you cannot run aggregations
in Atlas (you can — see the dashboard query below), it is that the
*long-running, multi-source, ML-shaped* analytics belong on the lakehouse.
"""

import os
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from pymongo import DESCENDING, MongoClient

load_dotenv()

MONGODB_URI = os.environ["MONGODB_URI"]
DB_NAME     = os.environ.get("DB_NAME", "atlas_databricks_demo")


def section(title: str) -> None:
    print()
    print("─" * 64)
    print(f"  {title}")
    print("─" * 64)


def timed(fn):
    start = time.perf_counter()
    result = fn()
    elapsed_ms = (time.perf_counter() - start) * 1000
    return result, elapsed_ms


def query_customer_with_orders(db, customer_id: str) -> None:
    """App pattern: 'show me this customer and their last 5 orders'."""
    section(f"Pattern 1 — Customer profile + recent orders  ({customer_id})")
    customer, ms_c = timed(lambda: db.customers.find_one({"customerId": customer_id}))
    if not customer:
        print(f"  Customer {customer_id} not found.")
        return
    orders, ms_o = timed(lambda: list(
        db.orders.find({"customerId": customer_id})
                 .sort("placedAt", DESCENDING)
                 .limit(5)
    ))
    print(f"  Customer  : {customer['name']}  ({customer['tier']}, {customer['region']})")
    print(f"  Email     : {customer['email']}")
    print(f"  Orders    : {len(orders)} returned in {ms_o:.1f} ms")
    for o in orders:
        print(f"    {o['orderId']}  {o['placedAt']:%Y-%m-%d}  "
              f"${o['total']:>8.2f}  {o['status']:<10}  {len(o['items'])} items")
    print(f"  Customer lookup latency: {ms_c:.1f} ms  |  Orders latency: {ms_o:.1f} ms")


def inventory_check(db, sku: str) -> None:
    """App pattern: 'is this SKU in stock right now?' — must be ms-fast."""
    section(f"Pattern 2 — Inventory check  ({sku})")
    product, ms = timed(lambda: db.products.find_one(
        {"sku": sku}, {"name": 1, "stock": 1, "price": 1, "attributes": 1}
    ))
    if not product:
        print(f"  SKU {sku} not found.")
        return
    print(f"  Product   : {product['name']}")
    print(f"  Price     : ${product['price']}")
    print(f"  In stock  : {product['stock']} units")
    print(f"  Attributes: {product['attributes']}")
    print(f"  Latency   : {ms:.1f} ms")


def place_order(db, customer_id: str, sku: str, qty: int = 1) -> None:
    """App pattern: write a new order as a single document, including all line items."""
    section(f"Pattern 3 — Place an order  (single-document write)")
    customer = db.customers.find_one({"customerId": customer_id})
    product  = db.products.find_one({"sku": sku})
    if not customer or not product:
        print("  Customer or product missing, skipping.")
        return
    line_total = round(product["price"] * qty, 2)
    order = {
        "orderId": f"O-DEMO-{int(time.time())}",
        "customerId": customer_id,
        "region": customer["region"],
        "status": "pending",
        "items": [{
            "sku": product["sku"], "name": product["name"],
            "category": product["category"], "qty": qty,
            "unitPrice": product["price"], "lineTotal": line_total,
        }],
        "subtotal": line_total,
        "tax": round(line_total * 0.08, 2),
        "total": round(line_total * 1.08, 2),
        "placedAt": datetime.now(timezone.utc),
    }
    _, ms = timed(lambda: db.orders.insert_one(order))
    print(f"  Inserted order {order['orderId']}  total ${order['total']}")
    print(f"  Latency   : {ms:.1f} ms")
    print("  Note: line items live inside the order document — no join needed at read time.")


def recent_activity(db, customer_id: str) -> None:
    """App pattern: 'my activity in the last 7 days' — uses the (customerId, ts) index."""
    section(f"Pattern 4 — Recent activity feed  ({customer_id}, last 7 days)")
    since = datetime.now(timezone.utc) - timedelta(days=7)
    events, ms = timed(lambda: list(
        db.events.find({"customerId": customer_id, "ts": {"$gte": since}})
                 .sort("ts", DESCENDING).limit(10)
    ))
    print(f"  Events returned: {len(events)}  in {ms:.1f} ms")
    for e in events[:5]:
        print(f"    {e['ts']:%Y-%m-%d %H:%M}  {e['eventType']:<15}  {e.get('productSku', '-')}")


def todays_revenue_dashboard(db) -> None:
    """
    App pattern: live operational dashboard widget.

    Atlas handles aggregations like this comfortably. The point is the *scope*:
    a single-tenant, recent-window summary that needs to refresh every few
    seconds. Multi-source historical analytics (cohort retention, LTV across
    all customers, ML feature engineering) is the Databricks workload.
    """
    section("Pattern 5 — Live revenue-by-region widget  (last 30 days)")
    since = datetime.now(timezone.utc) - timedelta(days=30)
    pipeline = [
        {"$match": {"placedAt": {"$gte": since}, "status": {"$ne": "cancelled"}}},
        {"$group": {"_id": "$region", "revenue": {"$sum": "$total"},
                    "orders": {"$sum": 1}}},
        {"$sort": {"revenue": -1}},
    ]
    results, ms = timed(lambda: list(db.orders.aggregate(pipeline)))
    print(f"  Aggregation latency: {ms:.1f} ms")
    print(f"  {'Region':<14} {'Orders':>8} {'Revenue':>12}")
    print(f"  {'─'*14} {'─'*8} {'─'*12}")
    for r in results:
        print(f"  {r['_id']:<14} {r['orders']:>8} {'$' + format(r['revenue'], ',.2f'):>12}")


def main():
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)
    db = client[DB_NAME]
    print(f"=== Atlas operational query patterns  |  {DB_NAME} ===")

    sample_customer = db.customers.find_one(sort=[("createdAt", -1)])["customerId"]
    sample_sku      = db.products.find_one()["sku"]

    query_customer_with_orders(db, sample_customer)
    inventory_check(db, sample_sku)
    place_order(db, sample_customer, sample_sku, qty=2)
    recent_activity(db, sample_customer)
    todays_revenue_dashboard(db)

    print()
    print("Takeaway: every query here is a millisecond-scale operational read or")
    print("write. Next step — export_to_s3.py — moves the same data to the lakehouse")
    print("boundary where Databricks takes over for warehouse-scale analytics.")
    client.close()


if __name__ == "__main__":
    main()
