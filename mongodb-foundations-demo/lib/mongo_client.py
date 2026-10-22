"""Connection helpers for the MongoDB Foundations walkthrough.

One cached client is shared by the Streamlit app, the seed script, the readiness
checks, and the tests. `MONGODB_URI` is the only configuration the demo reads;
the database and collection names are constants so no code path can be pointed
at a namespace this demo does not own.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv(Path(__file__).parent.parent / ".env")

# The single namespace this demo is allowed to create, write, and drop.
DB_NAME = "mongodb_foundations_demo"

CUSTOMERS = "customers"
ACCOUNTS = "accounts"
TRANSACTIONS = "transactions"
COLLECTIONS = [CUSTOMERS, ACCOUNTS, TRANSACTIONS]

# Command / query budgets. Kept short so a stalled cluster never hangs a demo.
SERVER_SELECTION_TIMEOUT_MS = 8_000
CONNECT_TIMEOUT_MS = 8_000
SOCKET_TIMEOUT_MS = 20_000
QUERY_TIMEOUT_MS = 10_000

APP_NAME = "mongodb-foundations-walkthrough"

_client = None  # type: MongoClient | None


class MissingUriError(RuntimeError):
    """Raised when MONGODB_URI is absent, so the UI can explain the fix."""


def uri_present() -> bool:
    """True when MONGODB_URI is set. Never returns or logs the value itself."""
    return bool(os.getenv("MONGODB_URI"))


def get_client() -> MongoClient:
    """Return the cached MongoClient built from MONGODB_URI."""
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise MissingUriError(
                "Missing MONGODB_URI. Copy .env.example to .env and set the "
                "connection string for an existing replica-set deployment."
            )
        _client = MongoClient(
            uri,
            appname=APP_NAME,
            serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
            connectTimeoutMS=CONNECT_TIMEOUT_MS,
            socketTimeoutMS=SOCKET_TIMEOUT_MS,
            retryWrites=True,
            w="majority",
        )
    return _client


def get_db() -> Database:
    """Return the dedicated demo database handle."""
    return get_client()[DB_NAME]


def db_name() -> str:
    return DB_NAME


def customers():
    return get_db()[CUSTOMERS]


def accounts():
    return get_db()[ACCOUNTS]


def transactions():
    return get_db()[TRANSACTIONS]


def ping() -> bool:
    """Best-effort connectivity check used by readiness checks and the UI."""
    try:
        get_client().admin.command("ping")
        return True
    except Exception:  # noqa: BLE001 — callers only need the boolean
        return False


def counts() -> dict:
    """Document count per demo collection."""
    db = get_db()
    return {name: db[name].count_documents({}) for name in COLLECTIONS}


def is_empty() -> bool:
    """True when the demo has not been seeded yet."""
    return get_db()[CUSTOMERS].count_documents({}, limit=1) == 0
