"""Seed the CropTrace demo data into MongoDB Atlas.

Idempotent: drops and re-creates the demo collections, applies the JSON Schema
validators, inserts synthetic plots / products / crops / treatment events /
residue predictions, and embeds the knowledge corpus so vector search works
immediately. Deterministic sizes keep demos and screenshots reproducible.

    python3 seed_data.py

After seeding, create the Atlas Vector Search index:

    python3 scripts/create_indexes.py
"""

from __future__ import annotations

from pymongo import ASCENDING, DESCENDING

from lib.atlas_client import COLLECTIONS, KNOWLEDGE_COLLECTION, db_name, get_db
from lib.embeddings import embedding_dim, get_embedder, provider_name
from lib.knowledge import NOTES, note_text
from lib.sample_data import (build_crops, build_plots_and_events,
                             build_products)
from lib.schema import apply_validators


def _create_btree_indexes(db) -> None:
    """Btree indexes aligned to the query patterns in lib/queries.py."""
    db.plots.create_index([("plot_id", ASCENDING)], unique=True)
    db.plots.create_index([("grower_id", ASCENDING)])
    db.crop_protection_products.create_index([("product_id", ASCENDING)],
                                             unique=True)
    db.treatment_events.create_index([("treatment_id", ASCENDING)], unique=True)
    db.treatment_events.create_index([("plot_id", ASCENDING),
                                      ("status", ASCENDING)])
    db.treatment_events.create_index([("product_ref", ASCENDING)])
    db.residue_predictions.create_index([("plot_id", ASCENDING)])
    db.audit_events.create_index([("plot_id", ASCENDING),
                                  ("created_at", DESCENDING)])
    db[KNOWLEDGE_COLLECTION].create_index([("note_id", ASCENDING)], unique=True)


def _embed_notes(notes: list[dict]) -> None:
    embedder = get_embedder()
    vectors = embedder.embed_documents([note_text(n) for n in notes])
    for note, vec in zip(notes, vectors):
        note["embedding"] = vec
        note["embedding_provider"] = embedder.provider
        note["embedding_dim"] = len(vec)


def seed() -> None:
    db = get_db()
    print(f"Connecting to Atlas, target database: {db_name()}")
    print(f"Embedding provider: {provider_name()} (dim={embedding_dim()})")

    print("Dropping existing demo collections (idempotent re-seed)...")
    for name in COLLECTIONS:
        db[name].drop()

    print("Applying JSON Schema validators (collMod/create)...")
    apply_validators(db)

    products = build_products()
    crops = build_crops()
    plots, events, predictions = build_plots_and_events(products)
    notes = [dict(n) for n in NOTES]

    print(f"Embedding {len(notes)} knowledge notes...")
    _embed_notes(notes)

    print(f"Inserting {len(plots)} plots, {len(products)} products, "
          f"{len(crops)} crops, {len(events)} treatment events, "
          f"{len(predictions)} residue predictions, {len(notes)} notes...")
    db.crop_protection_products.insert_many(products)
    db.crops.insert_many(crops)
    db.plots.insert_many(plots)
    db.treatment_events.insert_many(events)
    db.residue_predictions.insert_many(predictions)
    db[KNOWLEDGE_COLLECTION].insert_many(notes)

    _create_btree_indexes(db)

    print("Seed complete.")
    print(f"  Database : {db_name()}")
    print("  Next     : python3 scripts/create_indexes.py")
    print("  Then     : streamlit run app.py")


if __name__ == "__main__":
    seed()
