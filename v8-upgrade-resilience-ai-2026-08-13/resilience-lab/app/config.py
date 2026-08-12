"""Environment-driven configuration and the shared MongoDB client.

Every driver option that matters during a failover is exposed as an environment
variable so a workshop can re-run the same experiment with different settings
and compare the numbers. The cluster is assumed to exist already (see
../../atlas-cluster-provisioning); nothing here provisions anything.
"""
import os
from pathlib import Path

from pymongo import MongoClient

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:  # dotenv is optional; plain env vars work fine
    pass


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


DB_NAME = os.getenv("DB_NAME", "resilience_lab")
ORDERS_COLLECTION = os.getenv("ORDERS_COLLECTION", "orders")

# ── Driver options ──────────────────────────────────────────────────────────
RETRY_WRITES = _bool("RETRY_WRITES", True)
RETRY_READS = _bool("RETRY_READS", True)
SERVER_SELECTION_TIMEOUT_MS = _int("SERVER_SELECTION_TIMEOUT_MS", 5000)
CONNECT_TIMEOUT_MS = _int("CONNECT_TIMEOUT_MS", 5000)
SOCKET_TIMEOUT_MS = _int("SOCKET_TIMEOUT_MS", 10000)
MAX_POOL_SIZE = _int("MAX_POOL_SIZE", 20)
HEARTBEAT_FREQUENCY_MS = _int("HEARTBEAT_FREQUENCY_MS", 10000)
TIMEOUT_MS = _int("TIMEOUT_MS", 0)  # 0 = unset, driver default applies
WRITE_CONCERN = os.getenv("WRITE_CONCERN", "majority")
READ_PREFERENCE = os.getenv("READ_PREFERENCE", "primary")

# ── Load generator ──────────────────────────────────────────────────────────
WORKER_COUNT = _int("WORKER_COUNT", 2)
TARGET_OPS_PER_SECOND = _float("TARGET_OPS_PER_SECOND", 10.0)
READ_RATIO = _float("READ_RATIO", 0.5)
AUTOSTART = _bool("AUTOSTART", True)

# ── Metrics ─────────────────────────────────────────────────────────────────
METRICS_WINDOW_SECONDS = _int("METRICS_WINDOW_SECONDS", 30)
EVENT_LOG_SIZE = _int("EVENT_LOG_SIZE", 50)

# ── Service ─────────────────────────────────────────────────────────────────
HOST = os.getenv("HOST", "127.0.0.1")
PORT = _int("PORT", 8000)

_client = None


def client_options() -> dict:
    """The exact keyword arguments handed to MongoClient, for /status output."""
    opts = {
        "retryWrites": RETRY_WRITES,
        "retryReads": RETRY_READS,
        "serverSelectionTimeoutMS": SERVER_SELECTION_TIMEOUT_MS,
        "connectTimeoutMS": CONNECT_TIMEOUT_MS,
        "socketTimeoutMS": SOCKET_TIMEOUT_MS,
        "maxPoolSize": MAX_POOL_SIZE,
        "heartbeatFrequencyMS": HEARTBEAT_FREQUENCY_MS,
        "w": WRITE_CONCERN,
        "readPreference": READ_PREFERENCE,
        "appname": "resilience-lab",
    }
    if TIMEOUT_MS:
        opts["timeoutMS"] = TIMEOUT_MS
    return opts


def get_client() -> MongoClient:
    """Return a cached MongoClient built from MONGODB_URI."""
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise RuntimeError(
                "MONGODB_URI is not set. Export it, or copy .env.example to "
                ".env and fill it in."
            )
        opts = client_options()
        cert = os.getenv("MONGODB_CERT")
        if cert:
            opts.update(tls=True, tlsCertificateKeyFile=cert)
        _client = MongoClient(uri, **opts)
    return _client


def get_orders():
    return get_client()[DB_NAME][ORDERS_COLLECTION]
