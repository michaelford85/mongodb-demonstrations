"""Shared MongoDB Atlas connection helpers for the CropTrace architecture demo.

A single cached client is reused across the Streamlit app, the seed script, the
index helpers, and the tests. Collection names, demo vocabularies, and the
allowlist of presentable demo IDs live here so every module agrees on the
schema and no page can execute an arbitrary query against an arbitrary id.

CropTrace is an illustrative scenario for fruit and vegetable growers: it combines
treatment plans, weather, crop-protection-product data, and crop/plot
information to reason about residue risk at harvest. All data in this demo is
synthetic and every grower, plot, and product name is invented.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv(Path(__file__).parent.parent / ".env")

DEFAULT_DB_NAME = "croptrace_demo"

# ── Demo vocabularies (shared by seed data, queries, and the UI) ────────────
CROPS = ["Apple", "Grape", "Strawberry", "Tomato", "Lettuce", "Potato"]
REGIONS = ["Loire Valley", "Andalusia", "Po Valley", "Rhineland",
           "Alentejo", "Thessaly"]
SEASONS = ["2024 Spring", "2024 Summer", "2025 Spring", "2025 Summer"]
TREATMENT_STATUSES = ["planned", "applied", "cancelled"]
RISK_LEVELS = ["low", "moderate", "elevated", "high"]
PRODUCT_CATEGORIES = ["Fungicide", "Insecticide", "Herbicide", "Biocontrol"]

# ── Logical collections that make up the CropTrace workload ───────────────────
COLLECTIONS = [
    "plots",                     # embeds read-together treatment/weather/prediction
    "crop_protection_products",  # authoritative, frequently-updated master data
    "crops",                     # crop + variety reference data
    "treatment_events",          # normalized treatments for aggregation / $lookup
    "residue_predictions",       # normalized predictions for aggregation / $lookup
    "audit_events",              # written by the ACID transaction workflow
    "knowledge_notes",           # synthetic guidance corpus (carries embeddings)
]

# Collection that carries vector embeddings for the Knowledge Assistant.
KNOWLEDGE_COLLECTION = "knowledge_notes"

# Collections that carry a JSON Schema validator (see lib/schema.py).
VALIDATED_COLLECTIONS = ["plots", "crop_protection_products", "treatment_events"]

# Deterministic allowlist of demo ids the UI is permitted to act on. Pages only
# ever pass ids drawn from these lists — never free-form user input into a query.
PLOT_IDS = [f"PLOT-{i:03d}" for i in range(1, 13)]
GROWER_IDS = [f"GRW-{i:03d}" for i in range(1, 7)]
PRODUCT_IDS = [f"CPP-{i:03d}" for i in range(1, 9)]

_client: MongoClient | None = None


def get_client() -> MongoClient:
    """Return a cached MongoClient built from MONGODB_URI."""
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise ValueError(
                "Missing MONGODB_URI. Copy .env.example to .env and set your "
                "Atlas connection string (the cluster from "
                "atlas-cluster-provisioning)."
            )
        _client = MongoClient(uri, serverSelectionTimeoutMS=10_000,
                              appname="croptrace-demo")
    return _client


def get_db() -> Database:
    """Return the demo database handle."""
    return get_client()[db_name()]


def db_name() -> str:
    return os.getenv("MONGODB_DB_NAME", DEFAULT_DB_NAME)


def is_empty() -> bool:
    """True when the core collections have not been seeded yet."""
    return get_db().plots.count_documents({}, limit=1) == 0


def knowledge_has_embeddings() -> bool:
    """True when at least one knowledge note carries a vector embedding."""
    db = get_db()
    return db[KNOWLEDGE_COLLECTION].count_documents(
        {"embedding": {"$exists": True}}, limit=1) > 0


def ping() -> bool:
    """Best-effort connectivity check used by the readiness page and tests."""
    try:
        get_client().admin.command("ping")
        return True
    except Exception:
        return False
