"""Shared helpers for the Atlas → Iceberg reference-pattern demo.

Holds environment loading, structured logging, console banners, the MongoDB
Atlas client, change-stream eligibility checks, and durable resume-token
(checkpoint) storage. Iceberg/Trino specifics live in ``iceberg_io.py``.
"""

import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

# ── Paths ────────────────────────────────────────────────────────────────────
DEMO_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = DEMO_DIR / "state"
RESUME_TOKEN_FILE = STATE_DIR / "resume_token.json"

load_dotenv(DEMO_DIR / ".env")

# ── Configuration (env with safe local defaults) ───────────────────────────────
DB_NAME = os.getenv("DB_NAME", "atlas_iceberg_demo")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "orders")
SEED_ORDER_COUNT = int(os.getenv("SEED_ORDER_COUNT", "500"))

ICEBERG_REST_URI = os.getenv("ICEBERG_REST_URI", "http://localhost:8181")
ICEBERG_WAREHOUSE = os.getenv("ICEBERG_WAREHOUSE", "s3://warehouse/")
ICEBERG_NAMESPACE = os.getenv("ICEBERG_NAMESPACE", "demo")
ICEBERG_TABLE = os.getenv("ICEBERG_TABLE", "orders")

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET", "warehouse")

TRINO_HOST = os.getenv("TRINO_HOST", "localhost")
TRINO_PORT = int(os.getenv("TRINO_PORT", "8080"))
TRINO_USER = os.getenv("TRINO_USER", "demo")
TRINO_CATALOG = os.getenv("TRINO_CATALOG", "iceberg")


# ── Logging & console output ───────────────────────────────────────────────────
def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-5s %(name)s | %(message)s",
                              datefmt="%H:%M:%S")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def banner(title: str) -> None:
    """Presentation-friendly phase banner."""
    line = "═" * 68
    print(f"\n{line}\n  {title}\n{line}")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(
            f"Missing required environment variable: {name}. "
            "Copy .env.example to .env and fill in your values."
        )
    return value


# ── MongoDB Atlas ──────────────────────────────────────────────────────────────
def get_mongo_client() -> MongoClient:
    uri = require_env("MONGODB_URI")
    return MongoClient(uri, serverSelectionTimeoutMS=10_000,
                       w="majority", retryWrites=True)


def get_collection(client: MongoClient):
    return client[DB_NAME][COLLECTION_NAME]


def supports_change_streams(client: MongoClient) -> bool:
    """Change streams require a replica set or sharded cluster. Atlas always
    qualifies; a local standalone does not."""
    try:
        hello = client.admin.command("hello")
        return bool(hello.get("setName")) or hello.get("msg") == "isdbgrid"
    except Exception:
        return False


# ── Durable resume-token checkpoint (gitignored) ───────────────────────────────
def save_resume_token(token: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = RESUME_TOKEN_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(token, f)
    tmp.replace(RESUME_TOKEN_FILE)  # atomic swap so a crash never truncates it


def load_resume_token() -> dict | None:
    if not RESUME_TOKEN_FILE.exists():
        return None
    with open(RESUME_TOKEN_FILE) as f:
        return json.load(f)


def clear_resume_token() -> None:
    RESUME_TOKEN_FILE.unlink(missing_ok=True)
