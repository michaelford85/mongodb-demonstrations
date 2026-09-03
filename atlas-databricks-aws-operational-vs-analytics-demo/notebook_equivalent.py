"""
Reference: the PySpark equivalents of the workloads in analytics_simulation.py.

This file is illustrative only — it is not executed by the demo. It shows
what the same three analytics queries look like as they would actually be
written and scheduled inside a Databricks notebook, reading the JSONL
exported by export_to_s3.py from S3.

For a real deployment you would land the data as Delta tables via Databricks
Auto Loader and run queries against those tables. Two alternatives that
remove S3 from the path entirely are worth knowing about:

  - MongoDB Spark Connector: read Atlas collections directly from a
    Databricks cluster, no export step required.
  - Atlas SQL Interface + Databricks federation: query Atlas as a federated
    source. Useful for ad-hoc analytics that do not justify a Delta copy.

Each option has trade-offs around freshness, cost, and decoupling. The S3
+ Delta path used in this demo is the most decoupled and the most common
in AWS-centric enterprises.
"""

# ─────────────────────────────────────────────────────────────────────────
# Notebook setup (cell 1)
# ─────────────────────────────────────────────────────────────────────────
NOTEBOOK_SETUP = r'''
# Databricks notebook source
from pyspark.sql import functions as F

S3_BASE = "s3://my-bucket/atlas-exports/20260520T143000Z"

customers = spark.read.json(f"{S3_BASE}/customers.jsonl")
products  = spark.read.json(f"{S3_BASE}/products.jsonl")
orders    = spark.read.json(f"{S3_BASE}/orders.jsonl")
events    = spark.read.json(f"{S3_BASE}/events.jsonl")

# In production these would be Delta tables registered in Unity Catalog:
#   customers = spark.table("ecommerce.bronze.customers")
'''


# ─────────────────────────────────────────────────────────────────────────
# Analytics 1 — Customer Lifetime Value
# ─────────────────────────────────────────────────────────────────────────
ANALYTICS_LTV = r'''
ltv = (orders
    .filter(F.col("status") != "cancelled")
    .groupBy("customerId")
    .agg(F.sum("total").alias("ltv"),
         F.count("*").alias("orderCount"))
    .join(customers.select("customerId", "tier", "region"), "customerId")
    .orderBy(F.col("ltv").desc())
)
display(ltv.limit(10))
'''


# ─────────────────────────────────────────────────────────────────────────
# Analytics 2 — Revenue by category × region × month
# ─────────────────────────────────────────────────────────────────────────
ANALYTICS_CUBE = r'''
exploded = (orders
    .filter(F.col("status") != "cancelled")
    .withColumn("item", F.explode("items"))
    .withColumn("month", F.date_format("placedAt", "yyyy-MM"))
)

cube = (exploded
    .groupBy(F.col("item.category").alias("category"), "region", "month")
    .agg(F.sum("item.lineTotal").alias("revenue"))
    .orderBy(F.col("revenue").desc())
)
display(cube.limit(15))
'''


# ─────────────────────────────────────────────────────────────────────────
# Analytics 3 — Conversion funnel
# ─────────────────────────────────────────────────────────────────────────
ANALYTICS_FUNNEL = r'''
funnel = (events
    .filter(F.col("eventType").isin(
        "page_view", "add_to_cart", "checkout_start", "purchase"))
    .groupBy("eventType")
    .agg(F.countDistinct("customerId", "sessionId").alias("sessions"))
)
display(funnel)
'''


# ─────────────────────────────────────────────────────────────────────────
# Alternative: read Atlas directly via the MongoDB Spark Connector
# ─────────────────────────────────────────────────────────────────────────
SPARK_CONNECTOR = r'''
# pip install pymongo "pymongo[srv]" mongo-spark-connector

orders = (spark.read
    .format("mongodb")
    .option("connection.uri", dbutils.secrets.get("atlas", "uri"))
    .option("database", "atlas_databricks_demo")
    .option("collection", "orders")
    .load())

# No S3 in the path. Use when freshness > decoupling.
'''


if __name__ == "__main__":
    print(__doc__)
    print("Notebook setup:",       NOTEBOOK_SETUP)
    print("Analytics 1 — LTV:",    ANALYTICS_LTV)
    print("Analytics 2 — Cube:",   ANALYTICS_CUBE)
    print("Analytics 3 — Funnel:", ANALYTICS_FUNNEL)
    print("Direct Atlas read:",    SPARK_CONNECTOR)
