"""
Demonstrates the database-per-tenant isolation pattern on a shared Atlas cluster.

sample_mflix acts as an existing Tenant A database (real data, no inserts needed).
The script creates a lightweight Tenant B database to show the isolation side-by-side,
then cleans it up at the end.
"""

import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.environ["MONGODB_URI"]

TENANT_A_DB = "sample_mflix"     # pre-existing sample dataset
TENANT_B_DB = "demo_tenant_b"    # created and destroyed by this script


def divider(title):
    print(f"\n{'─'*62}")
    print(f"  {title}")
    print(f"{'─'*62}")


def main():
    client = MongoClient(MONGODB_URI)

    # ── Setup: create Tenant B ──────────────────────────────────────
    divider("Setup — creating Tenant B database")

    tenant_b = client[TENANT_B_DB]
    tenant_b.config.insert_one({
        "tenant_id": "tenant_b",
        "plan": "standard",
        "active": True,
    })
    tenant_b.catalog.insert_many([
        {"item_id": "B001", "name": "Item One",   "category": "alpha"},
        {"item_id": "B002", "name": "Item Two",   "category": "beta"},
        {"item_id": "B003", "name": "Item Three", "category": "alpha"},
    ])
    print(f"  Created '{TENANT_B_DB}' with 'config' and 'catalog' collections.")

    # ── Namespace view ──────────────────────────────────────────────
    divider("Namespace isolation — tenant databases on the cluster")

    all_dbs = client.list_database_names()
    tenant_dbs = [db for db in all_dbs if db in (TENANT_A_DB, TENANT_B_DB)]
    for db_name in sorted(tenant_dbs):
        collections = client[db_name].list_collection_names()
        print(f"\n  {db_name}/")
        for coll in sorted(collections):
            count = client[db_name][coll].estimated_document_count()
            print(f"    └─ {coll:<28} ({count:,} documents)")

    # ── Tenant A query ──────────────────────────────────────────────
    divider("Query: Tenant A (sample_mflix) — movies from 2010")

    tenant_a = client[TENANT_A_DB]
    movies = list(
        tenant_a.movies
        .find({"year": 2010}, {"title": 1, "genres": 1, "_id": 0})
        .sort("title", 1)
        .limit(5)
    )
    for m in movies:
        genres = ", ".join(m.get("genres", []))
        print(f"  {m['title']:<45}  [{genres}]")

    # ── Tenant B query ──────────────────────────────────────────────
    divider("Query: Tenant B — catalog items")

    items = list(tenant_b.catalog.find({}, {"_id": 0}).sort("item_id", 1))
    for item in items:
        print(f"  {item['item_id']}  {item['name']:<20}  category={item['category']}")

    # ── Isolation check ─────────────────────────────────────────────
    divider("Isolation check — querying 'movies' from Tenant B's database")

    cross_result = list(tenant_b.movies.find().limit(1))
    if cross_result:
        print("  [UNEXPECTED] Documents found — isolation broken!")
    else:
        print("  Result: 0 documents.")
        print("  Tenant B has no 'movies' collection. Tenant A's data is")
        print("  completely invisible from Tenant B's database namespace.")

    # ── Connection pattern ──────────────────────────────────────────
    divider("Connection pattern — how a multi-tenant application routes requests")

    base = MONGODB_URI.split("/?")[0]
    print(f"  Same cluster, same credentials, different database in the URI:\n")
    print(f"  Tenant A  →  {base}/{TENANT_A_DB}?...")
    print(f"  Tenant B  →  {base}/{TENANT_B_DB}?...")
    print()
    print("  The application resolves the correct database name from a tenant ID")
    print("  (e.g. from a JWT claim or a subdomain) and selects client[db_name].")
    print("  No query ever crosses a tenant boundary.")

    # ── Cleanup ─────────────────────────────────────────────────────
    divider("Cleanup — dropping Tenant B database")

    client.drop_database(TENANT_B_DB)
    print(f"  '{TENANT_B_DB}' dropped. Tenant A (sample_mflix) is unchanged.")

    client.close()


if __name__ == "__main__":
    main()
