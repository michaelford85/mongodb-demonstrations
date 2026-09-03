"""Seed the Product Catalog Studio demo data into MongoDB Atlas.

Idempotent: drops and re-creates only this demo's `pcs_*` collections, inserts
the fictional Kestrel Labworks catalog, embeds every product so semantic and
hybrid search work immediately, and creates the btree indexes the explorer
queries rely on. Deterministic content keeps demos and screenshots reproducible.

    python3 seed_data.py

After seeding, create the Atlas Search + Vector Search indexes:

    python3 scripts/create_indexes.py
"""

from __future__ import annotations

from pymongo import ASCENDING, DESCENDING

from lib.atlas_client import (COLLECTIONS, EVENTS_COLLECTION,
                              PRODUCTS_COLLECTION, db_name, get_db)
from lib.embeddings import embedding_dim, get_embedder, provider_name
from lib.sample_data import build_products


def _create_btree_indexes(db) -> None:
    """Btree indexes aligned to the filters and sorts in lib/catalog.py."""
    products = db[PRODUCTS_COLLECTION]
    products.create_index([("product_id", ASCENDING)], unique=True)
    products.create_index([("sku", ASCENDING)], unique=True)
    products.create_index([("product_type", ASCENDING), ("category", ASCENDING),
                           ("status", ASCENDING)])
    products.create_index([("price.amount", ASCENDING)])
    products.create_index([("updated_at", DESCENDING)])
    db[EVENTS_COLLECTION].create_index([("at", DESCENDING)])


def _embed_products(docs: list[dict]) -> None:
    from lib.embeddings import product_text

    embedder = get_embedder()
    vectors = embedder.embed_documents([product_text(d) for d in docs])
    for doc, vec in zip(docs, vectors):
        doc["embedding"] = vec
        doc["embedding_provider"] = embedder.provider
        doc["embedding_dim"] = len(vec)


def seed() -> None:
    db = get_db()
    print(f"Connecting to Atlas, target database: {db_name()}")
    print(f"Embedding provider: {provider_name()} (dim={embedding_dim()})")

    print("Dropping existing demo collections (idempotent re-seed)...")
    for name in COLLECTIONS:
        db[name].drop()

    docs = build_products()
    print(f"Embedding {len(docs)} products...")
    _embed_products(docs)

    print(f"Inserting {len(docs)} products into {PRODUCTS_COLLECTION}...")
    db[PRODUCTS_COLLECTION].insert_many(docs)

    _create_btree_indexes(db)

    print("Seed complete.")
    print(f"  Database : {db_name()}")
    print("  Next     : python3 scripts/create_indexes.py")
    print("  Then     : streamlit run app.py")


if __name__ == "__main__":
    seed()
