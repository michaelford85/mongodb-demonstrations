"""Shared MongoDB Atlas connection helpers for the Field Advisor demo.

A single cached client is reused across the app, the seed script, and the
index helper. Collection names and demo vocabularies live here so every module
agrees on the schema and the structured-filter options.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv(Path(__file__).parent.parent / ".env")

DEFAULT_DB_NAME = "field_advisor"

# Structured-filter vocabularies shared by seed data, queries, and the UI.
CROPS = ["Corn", "Soybean", "Wheat", "Cotton", "Rice", "Canola"]
REGIONS = ["Midwest", "Great Plains", "Pacific Northwest",
           "Southeast", "Mountain West"]
SEASONS = ["Pre-plant", "Planting", "Vegetative", "Flowering", "Harvest"]
PRODUCT_LINES = ["Seed Treatment", "Fungicide", "Herbicide",
                 "Insecticide", "Biologicals", "Digital Agronomy"]
SEVERITIES = ["Low", "Medium", "High", "Critical"]

# Logical collections that make up the advisory workload.
COLLECTIONS = [
    "growers",
    "fields",
    "products",
    "support_cases",
    "knowledge_articles",
    "interaction_history",
]

# Collection that carries vector embeddings for semantic retrieval.
KNOWLEDGE_COLLECTION = "knowledge_articles"

_client: MongoClient | None = None


def get_client() -> MongoClient:
    """Return a cached MongoClient built from MONGODB_URI."""
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise ValueError(
                "Missing MONGODB_URI. Copy .env.example to .env and set your "
                "Atlas connection string."
            )
        _client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
    return _client


def get_db() -> Database:
    """Return the demo database handle."""
    return get_client()[db_name()]


def db_name() -> str:
    return os.getenv("MONGODB_DB_NAME", DEFAULT_DB_NAME)


def is_empty() -> bool:
    """True when the core collections have not been seeded yet."""
    return get_db().growers.count_documents({}, limit=1) == 0


def knowledge_has_embeddings() -> bool:
    """True when at least one knowledge article carries a vector embedding."""
    db = get_db()
    return db[KNOWLEDGE_COLLECTION].count_documents(
        {"embedding": {"$exists": True}}, limit=1) > 0
