"""Shared MongoDB Atlas connection helpers for Product Catalog Studio.

A single cached client is reused across the Streamlit app, the seed script, the
index helpers, and the tests. Collection names, the product-type vocabularies,
and the structured-filter options live here so every module agrees on the shape
of a product document.

Kestrel Labworks is an invented brand used only for this demonstration. Every
product, SKU, and price in this demo is fictional.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv(Path(__file__).parent.parent / ".env")

BRAND = "Kestrel Labworks"
DEFAULT_DB_NAME = "product_catalog_studio"

# Collections are namespaced with a `pcs_` prefix so this demo can share a
# cluster (or even a database) with other demos without colliding.
PRODUCTS_COLLECTION = "pcs_products"
EVENTS_COLLECTION = "pcs_product_events"
COLLECTIONS = [PRODUCTS_COLLECTION, EVENTS_COLLECTION]

# ── Product-type vocabularies (shared by seed data, queries, and the UI) ────
PRODUCT_TYPES = ["equipment", "consumable", "service_plan"]
TYPE_LABELS = {"equipment": "Equipment", "consumable": "Consumable",
               "service_plan": "Service plan"}

CATEGORIES = {
    "equipment": ["Sample Preparation", "Measurement", "Environmental Control"],
    "consumable": ["Reagents", "Labware", "Filtration"],
    "service_plan": ["Support", "Calibration", "Training"],
}
ALL_CATEGORIES = sorted({c for v in CATEGORIES.values() for c in v})

STATUSES = ["active", "limited", "preorder", "discontinued"]
CURRENCY = "USD"

# One type-specific attribute per product type, used by the structured filter
# on the explorer and by every search mode.
TYPE_ATTRIBUTE = {
    "equipment": ("specs.power_source", "Power source",
                  ["Mains 120V", "Mains 230V", "Battery", "Pneumatic"]),
    "consumable": ("handling.hazard_class", "Hazard class",
                   ["None", "Irritant", "Flammable", "Corrosive"]),
    "service_plan": ("coverage.response_tier", "Response tier",
                     ["Next business day", "Same day", "4-hour", "Remote only"]),
}

_client: MongoClient | None = None


def get_client() -> MongoClient:
    """Return a cached MongoClient built from MONGODB_URI."""
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise ValueError(
                "Missing MONGODB_URI. Copy .env.example to .env and set your "
                "Atlas connection string (an existing cluster — this demo "
                "never provisions one)."
            )
        _client = MongoClient(uri, serverSelectionTimeoutMS=10_000,
                              appname="product-catalog-studio-demo")
    return _client


def get_db() -> Database:
    """Return the demo database handle."""
    return get_client()[db_name()]


def db_name() -> str:
    return os.getenv("MONGODB_DB_NAME", DEFAULT_DB_NAME)


def products():
    return get_db()[PRODUCTS_COLLECTION]


def events():
    return get_db()[EVENTS_COLLECTION]


def is_empty() -> bool:
    """True when the product collection has not been seeded yet."""
    return products().count_documents({}, limit=1) == 0


def products_have_embeddings() -> bool:
    """True when at least one product carries a vector embedding."""
    return products().count_documents({"embedding": {"$exists": True}},
                                      limit=1) > 0


def ping() -> bool:
    """Best-effort connectivity check used by the readiness page and tests."""
    try:
        get_client().admin.command("ping")
        return True
    except Exception:
        return False
