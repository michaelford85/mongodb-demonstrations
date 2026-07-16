"""Seed the Field Advisor demo data into MongoDB Atlas.

Creates growers, fields, products, support_cases, interaction_history, and a
synthetic agronomy knowledge base. Knowledge articles are embedded with the
configured provider (local by default) so vector search works immediately.
Re-running drops and re-seeds the demo database for reproducible runs.

    python3 seed_data.py                 # default sizes
    python3 seed_data.py --growers 40

After seeding, create the search indexes:

    python3 scripts/create_indexes.py
"""

import argparse

from pymongo import ASCENDING, DESCENDING

from lib.atlas_client import (COLLECTIONS, KNOWLEDGE_COLLECTION, db_name,
                              get_db)
from lib.embeddings import (article_text, embedding_dim, get_embedder,
                            provider_name)
from lib.sample_data import (build_fields, build_growers,
                             build_knowledge_articles, build_products,
                             build_support_cases)


def _create_indexes(db) -> None:
    """Standard btree indexes aligned to the query patterns in lib/queries.py."""
    db.growers.create_index([("grower_id", ASCENDING)], unique=True)
    db.fields.create_index([("field_id", ASCENDING)], unique=True)
    db.fields.create_index([("grower_id", ASCENDING)])
    db.products.create_index([("product_id", ASCENDING)], unique=True)
    db.support_cases.create_index([("case_id", ASCENDING)], unique=True)
    db.support_cases.create_index([("grower_id", ASCENDING), ("updated_at", DESCENDING)])
    # Structured-filter read pattern used by advisory search + case lists.
    db.support_cases.create_index([("crop", ASCENDING), ("region", ASCENDING),
                                   ("season", ASCENDING)])
    db.interaction_history.create_index([("grower_id", ASCENDING),
                                         ("created_at", DESCENDING)])
    db.interaction_history.create_index([("case_id", ASCENDING)])
    db[KNOWLEDGE_COLLECTION].create_index([("article_id", ASCENDING)], unique=True)


def _embed_articles(articles: list[dict]) -> None:
    """Attach a vector embedding to each knowledge article, in place."""
    embedder = get_embedder()
    vectors = embedder.embed_documents([article_text(a) for a in articles])
    for art, vec in zip(articles, vectors):
        art["embedding"] = vec
        art["embedding_provider"] = embedder.provider
        art["embedding_dim"] = len(vec)


def seed(growers_n: int) -> None:
    db = get_db()
    print(f"Connecting to Atlas, target database: {db_name()}")
    print(f"Embedding provider: {provider_name()} (dim={embedding_dim()})")

    print("Dropping existing demo collections (idempotent re-seed)...")
    for name in COLLECTIONS:
        db[name].drop()

    growers = build_growers(growers_n)
    fields = build_fields(growers)
    products = build_products()
    cases, history = build_support_cases(growers, fields, products)
    articles = build_knowledge_articles()

    print(f"Embedding {len(articles)} knowledge articles...")
    _embed_articles(articles)

    print(f"Inserting {len(growers)} growers, {len(fields)} fields, "
          f"{len(products)} products, {len(cases)} support cases, "
          f"{len(history)} interactions, {len(articles)} knowledge articles...")
    db.growers.insert_many(growers)
    db.fields.insert_many(fields)
    db.products.insert_many(products)
    if cases:
        db.support_cases.insert_many(cases)
    if history:
        db.interaction_history.insert_many(history)
    db[KNOWLEDGE_COLLECTION].insert_many(articles)

    _create_indexes(db)

    print("Seed complete.")
    print(f"  Database : {db_name()}")
    print("  Next     : python3 scripts/create_indexes.py")
    print("  Then     : streamlit run app.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Field Advisor demo data")
    parser.add_argument("--growers", type=int, default=24,
                        help="Number of synthetic growers (default: 24)")
    args = parser.parse_args()
    seed(args.growers)


if __name__ == "__main__":
    main()
