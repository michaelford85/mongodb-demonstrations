"""Shared MongoDB connection and lab configuration.

Every value is driven by .env so the CLI and the mongosh snippets in the
README agree on the same namespace. The cluster is assumed to exist already
(see ../atlas-cluster-provisioning) — nothing here provisions anything.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).parent.parent / ".env")

_client = None

DB_NAME = os.getenv("DB_NAME", "version_8_lab")
ORDERS_COLLECTION = os.getenv("ORDERS_COLLECTION", "orders")
CUSTOMERS_COLLECTION = os.getenv("CUSTOMERS_COLLECTION", "customers")

# Index the query-settings demo pins queries to.
ORDER_DATE_INDEX = "order_date_1"

DATA_DIR = Path(__file__).parent.parent / "data"


def get_client() -> MongoClient:
    """Return a cached MongoClient, honouring optional X.509 cert auth."""
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise RuntimeError(
                "MONGODB_URI is not set. Copy .env.example to .env and fill it in."
            )
        cert = os.getenv("MONGODB_CERT")
        if cert:
            _client = MongoClient(uri, tls=True, tlsCertificateKeyFile=cert)
        else:
            _client = MongoClient(uri)
    return _client


def get_db():
    return get_client()[DB_NAME]


def get_orders():
    return get_db()[ORDERS_COLLECTION]


def get_customers():
    return get_db()[CUSTOMERS_COLLECTION]


def server_version() -> tuple:
    """Return the server version as a tuple of ints, e.g. (8, 0, 4)."""
    raw = get_client().admin.command("buildInfo")["version"]
    parts = []
    for piece in raw.split("."):
        digits = "".join(c for c in piece if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def require_v8() -> tuple:
    """Fail loudly rather than showing a confusing error on a 7.x cluster."""
    version = server_version()
    if version < (8, 0):
        raise SystemExit(
            f"This demo needs MongoDB 8.0 or later; the cluster reports "
            f"{'.'.join(str(p) for p in version)}."
        )
    return version
