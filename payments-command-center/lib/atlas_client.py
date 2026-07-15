"""Shared MongoDB Atlas connection helpers for Northstar Payments Command Center.

A single cached client is reused across the app, the seed script, and the
simulator. Collection names live here so every module agrees on the schema.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv(Path(__file__).parent.parent / ".env")

DEFAULT_DB_NAME = "northstar_payments"

# Regions used across seed data, the simulator, and the dashboard.
REGIONS = ["us-east", "us-west", "eu-west", "ap-southeast", "sa-east"]

# The three payment event shapes the demo tells a story around.
PAYMENT_TYPES = ["card_present", "wallet_token", "installment"]

# Logical collections that make up the authorization workload.
COLLECTIONS = [
    "accounts",
    "payment_instruments",
    "merchants",
    "auth_requests",
    "auth_decisions",
    "ledger_events",
    "balance_snapshots",
]

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
    db_name = os.getenv("MONGODB_DB_NAME", DEFAULT_DB_NAME)
    return get_client()[db_name]


def db_name() -> str:
    return os.getenv("MONGODB_DB_NAME", DEFAULT_DB_NAME)


def default_region() -> str:
    return os.getenv("SIMULATION_DEFAULT_REGION", REGIONS[0])


def batch_size() -> int:
    return int(os.getenv("SIMULATION_BATCH_SIZE", "4"))


def is_empty() -> bool:
    """True when the core collections have not been seeded yet."""
    db = get_db()
    return db.accounts.count_documents({}, limit=1) == 0


def supports_change_streams() -> bool:
    """Change streams need a replica set. Atlas always qualifies, but a local
    standalone does not — this lets the UI fall back to polling gracefully."""
    try:
        client = get_client()
        hello = client.admin.command("hello")
        return bool(hello.get("setName")) or hello.get("msg") == "isdbgrid"
    except Exception:
        return False
