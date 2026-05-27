"""
Simulates the Databricks side of the architecture by reading the exported
JSONL files and running three analytics-shaped workloads:

  1. Customer lifetime value (LTV) — full-history per-customer aggregation
  2. Category × region × month revenue — wide cross-tab
  3. Conversion funnel — multi-event-type behavioural analysis

These are deliberately not workloads you would point a live transactional
application at. They scan the whole dataset, join across collections, and
produce wide tabular outputs — the shape Databricks/Spark is designed for.

Implementation note: this runs in plain Python so the repo stays dependency-
light. Treat the code as a stand-in for what would actually be a PySpark
or Spark SQL notebook reading the same files from S3 as a Delta table.
See notebook_equivalent.py for the equivalent PySpark snippets.

Reads from ./_s3_export/ by default; reads from S3 if AWS_S3_BUCKET is set.
"""

import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

AWS_REGION    = os.environ.get("AWS_REGION", "us-east-1")
AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET", "").strip()
AWS_S3_PREFIX = os.environ.get("AWS_S3_PREFIX", "atlas-exports/").rstrip("/") + "/"
LOCAL_DIR     = Path(__file__).parent / "_s3_export"


def section(title: str) -> None:
    print()
    print("─" * 64)
    print(f"  {title}")
    print("─" * 64)


def latest_local_batch() -> Path:
    if not LOCAL_DIR.exists():
        raise SystemExit(f"No exports found at {LOCAL_DIR}. Run export_to_s3.py first.")
    batches = sorted([p for p in LOCAL_DIR.iterdir() if p.is_dir()])
    if not batches:
        raise SystemExit(f"No batches under {LOCAL_DIR}. Run export_to_s3.py first.")
    return batches[-1]


def load_jsonl_local(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def load_jsonl_s3(key: str) -> list[dict]:
    import boto3
    s3 = boto3.client("s3", region_name=AWS_REGION)
    obj = s3.get_object(Bucket=AWS_S3_BUCKET, Key=key)
    text = obj["Body"].read().decode("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def load_all() -> dict:
    """Returns dict of collection_name → list[dict]. Mirrors a Spark DataFrame load."""
    if AWS_S3_BUCKET:
        import boto3
        s3 = boto3.client("s3", region_name=AWS_REGION)
        paginator = s3.get_paginator("list_objects_v2")
        latest_batch = None
        for page in paginator.paginate(Bucket=AWS_S3_BUCKET, Prefix=AWS_S3_PREFIX, Delimiter="/"):
            for cp in page.get("CommonPrefixes", []):
                latest_batch = cp["Prefix"]
        if not latest_batch:
            raise SystemExit(f"No batches found under s3://{AWS_S3_BUCKET}/{AWS_S3_PREFIX}")
        print(f"  Reading from s3://{AWS_S3_BUCKET}/{latest_batch}")
        return {coll: load_jsonl_s3(f"{latest_batch}{coll}.jsonl")
                for coll in ("customers", "products", "orders", "events")}

    batch = latest_local_batch()
    print(f"  Reading from {batch}  (local S3 stand-in)")
    return {coll: load_jsonl_local(batch / f"{coll}.jsonl")
            for coll in ("customers", "products", "orders", "events")}


def customer_lifetime_value(customers, orders) -> None:
    section("Analytics 1 — Customer Lifetime Value (per-customer, all history)")
    revenue = defaultdict(float)
    order_count = defaultdict(int)
    for o in orders:
        if o["status"] == "cancelled":
            continue
        revenue[o["customerId"]] += o["total"]
        order_count[o["customerId"]] += 1
    by_id = {c["customerId"]: c for c in customers}
    top = sorted(revenue.items(), key=lambda kv: kv[1], reverse=True)[:10]
    print(f"  Top 10 customers by lifetime spend (of {len(revenue)} with orders):")
    print(f"  {'Customer':<14} {'Tier':<10} {'Region':<14} {'Orders':>7} {'LTV':>12}")
    print(f"  {'─'*14} {'─'*10} {'─'*14} {'─'*7} {'─'*12}")
    for cid, ltv in top:
        c = by_id.get(cid, {})
        print(f"  {cid:<14} {c.get('tier', '?'):<10} {c.get('region', '?'):<14} "
              f"{order_count[cid]:>7} {'$' + format(ltv, ',.2f'):>12}")


def category_region_month_revenue(orders) -> None:
    section("Analytics 2 — Revenue by category × region × month")
    cube = defaultdict(float)
    for o in orders:
        if o["status"] == "cancelled":
            continue
        placed = datetime.fromisoformat(o["placedAt"].replace("Z", "+00:00"))
        month = placed.strftime("%Y-%m")
        for item in o["items"]:
            cube[(item["category"], o["region"], month)] += item["lineTotal"]
    rows = sorted(cube.items(), key=lambda kv: kv[1], reverse=True)[:15]
    print(f"  Top 15 cells of the category × region × month cube:")
    print(f"  {'Category':<12} {'Region':<14} {'Month':<8} {'Revenue':>12}")
    print(f"  {'─'*12} {'─'*14} {'─'*8} {'─'*12}")
    for (cat, region, month), rev in rows:
        print(f"  {cat:<12} {region:<14} {month:<8} {'$' + format(rev, ',.2f'):>12}")


def conversion_funnel(events) -> None:
    section("Analytics 3 — Behavioural conversion funnel")
    stages = ["page_view", "add_to_cart", "checkout_start", "purchase"]
    by_stage = defaultdict(set)  # set of (customerId, sessionId) pairs per stage
    for e in events:
        if e["eventType"] in stages:
            by_stage[e["eventType"]].add((e["customerId"], e["sessionId"]))
    print(f"  Distinct (customer, session) pairs reaching each stage:")
    print(f"  {'Stage':<18} {'Sessions':>10} {'% of top':>10}")
    print(f"  {'─'*18} {'─'*10} {'─'*10}")
    top = len(by_stage[stages[0]]) or 1
    for s in stages:
        n = len(by_stage[s])
        print(f"  {s:<18} {n:>10} {n / top * 100:>9.1f}%")


def main():
    print("=== Databricks-shaped analytics over the S3 export ===")
    print("    (running in plain Python; see notebook_equivalent.py for PySpark)")
    print()
    data = load_all()
    print(f"  Loaded: {len(data['customers'])} customers, "
          f"{len(data['products'])} products, {len(data['orders'])} orders, "
          f"{len(data['events'])} events")

    customer_lifetime_value(data["customers"], data["orders"])
    category_region_month_revenue(data["orders"])
    conversion_funnel(data["events"])

    print()
    print("Takeaway: every workload here scanned the full dataset and produced")
    print("a wide tabular result. In production these run on a Databricks cluster")
    print("over Delta tables backed by the same S3 bucket — at petabyte scale,")
    print("with notebook-driven authoring, scheduled jobs, BI connectivity, and")
    print("MLflow for model training. Atlas serves the live application; the")
    print("lakehouse serves the analyst, the data scientist, and the BI consumer.")


if __name__ == "__main__":
    main()
