"""Configuration, connection handling, and collection names for the demo.

The connection string is read ONLY from this demo folder's ``.env`` via the
``MONGODB_URI`` variable (the convention used across this repository). The
value is never logged, displayed, or embedded in error messages.

All reads and writes are confined to the dedicated demo database selected by
``DEMO_DATABASE`` (default ``smb_number_demo``). The connection string's own
default database is deliberately ignored so the app can never touch an
existing application or customer database by accident.

Every record used here is synthetic demo data with fictional telephone
numbers drawn from a reserved fictional range.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv(Path(__file__).parent.parent / ".env")

# ── Demo database & collections (the ONLY database this app touches) ────────
DEFAULT_DEMO_DB = "smb_number_demo"

ACCOUNTS_COLLECTION = "accounts"
NUMBER_ASSETS_COLLECTION = "numberAssets"
COUNTERS_COLLECTION = "provisioningCounters"  # demo/design recommendation
AUDIT_COLLECTION = "provisioningAudit"        # demo/design recommendation
COLLECTIONS = [
    ACCOUNTS_COLLECTION,
    NUMBER_ASSETS_COLLECTION,
    COUNTERS_COLLECTION,
    AUDIT_COLLECTION,
]

# Synthetic seed account ids used across pages and tests.
RACE_ACCOUNT_ID = "ACC-SMB-RACE"
SEED_ACCOUNT_IDS = ["ACC-SMB-0001", "ACC-SMB-0002", "ACC-ENT-0042",
                    RACE_ACCOUNT_ID]

_client: MongoClient | None = None


def db_name() -> str:
    """Demo database name (never derived from the connection string)."""
    return os.getenv("DEMO_DATABASE", "").strip() or DEFAULT_DEMO_DB


def get_client() -> MongoClient:
    """Return a cached MongoClient built from MONGODB_URI (never logged)."""
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI", "").strip()
        if not uri:
            raise ValueError(
                "Missing MONGODB_URI. Copy .env.example to .env in this demo "
                "folder and set your connection string. This demo never "
                "provisions infrastructure."
            )
        _client = MongoClient(uri, serverSelectionTimeoutMS=10_000,
                              appname="smb-number-provisioning-demo")
    return _client


def get_db() -> Database:
    """Return a handle to the dedicated demo database only."""
    return get_client()[db_name()]


def collections() -> dict[str, str]:
    """Exact collection names, shown in the UI for console inspection."""
    return {
        "accounts (account records)": ACCOUNTS_COLLECTION,
        "numberAssets (one telephone-number asset per document)":
            NUMBER_ASSETS_COLLECTION,
        "provisioningCounters (demo/design recommendation)":
            COUNTERS_COLLECTION,
        "provisioningAudit (demo/design recommendation)": AUDIT_COLLECTION,
    }


def supports_transactions(client: MongoClient) -> bool:
    """True when the connected deployment can run multi-document transactions
    (replica set or sharded cluster). Standalone deployments cannot."""
    try:
        hello = client.admin.command("hello")
        return bool(hello.get("setName")) or hello.get("msg") == "dbgrid"
    except Exception:
        return False


def execution_mode(client: MongoClient) -> str:
    """Human-readable label for the write path chosen at runtime."""
    return ("multi-document transactions (atomic)"
            if supports_transactions(client)
            else "reservation + compensation (non-atomic fallback)")
