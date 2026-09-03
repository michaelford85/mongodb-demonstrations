"""Environment-driven configuration for the support agent lab.

Nothing here provisions a cluster — see ../../atlas-cluster-provisioning. Every
external endpoint (MongoDB, the LLM, the embedding provider) is selected by
environment variable, and no secret is ever written to disk by this lab.

The LLM is pluggable so the lab can run in three ways:

  * LLM_PROVIDER=openai     real planning and real summaries
  * LLM_PROVIDER=anthropic  ditto
  * LLM_PROVIDER=offline    a deterministic rule-based planner, no key, no
                            network. The agent loop, the tool calls, and the
                            session memory are all genuine; only the language
                            model is replaced.
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


# ── Namespace ─────────────────────────────────────────────────────────────────
DB_NAME = os.getenv("DB_NAME", "agent_lab")
TICKETS_COLLECTION = os.getenv("TICKETS_COLLECTION", "tickets")
VECTOR_INDEX = os.getenv("VECTOR_INDEX", "tickets_vector_index")

EMBEDDING_FIELD = "embedding"
TEXT_FIELD = "description"

# ── LLM provider ──────────────────────────────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "offline").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE = _float("LLM_TEMPERATURE", 0.0)
LLM_MAX_TOKENS = _int("LLM_MAX_TOKENS", 700)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip()  # for gateways/proxies

# ── Embedding provider (optional — only for semantic ticket search) ───────────
# "offline" is the default so a workshop needs no keys at all.
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "offline").strip().lower()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "voyage-3.5")
EMBEDDING_DIM = _int("EMBEDDING_DIM", 256)
EMBEDDING_BATCH_SIZE = _int("EMBEDDING_BATCH_SIZE", 64)

# Semantic search needs both embeddings in the documents and an Atlas vector
# index. When off, search_tickets falls back to a regex scan, which is fine at
# this data volume and keeps the lab runnable on any tier.
USE_VECTOR_SEARCH = _bool("USE_VECTOR_SEARCH", False)

# ── Agent behaviour ───────────────────────────────────────────────────────────
# How many tool calls the agent may make for a single user turn before it must
# answer. Keeps a mis-planned loop bounded and visible.
MAX_STEPS = _int("MAX_STEPS", 4)
# Turns of conversation retained as short-term memory.
MEMORY_TURNS = _int("MEMORY_TURNS", 8)
DEFAULT_LIMIT = _int("DEFAULT_LIMIT", 5)
SHOW_TRACE = _bool("SHOW_TRACE", True)

DATA_FILE = Path(__file__).parent.parent / "data" / "tickets.json"

_client = None


def llm_api_key() -> str:
    """The LLM key, or an empty string when running offline."""
    return os.getenv("LLM_API_KEY", "").strip()


def embedding_api_key() -> str:
    """The embedding key, or an empty string when running offline."""
    return os.getenv("EMBEDDING_API_KEY", "").strip()


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
        opts = {"appname": "agent-lab"}
        cert = os.getenv("MONGODB_CERT")
        if cert:
            opts.update(tls=True, tlsCertificateKeyFile=cert)
        _client = MongoClient(uri, **opts)
    return _client


def get_tickets():
    return get_client()[DB_NAME][TICKETS_COLLECTION]


def namespace() -> str:
    return f"{DB_NAME}.{TICKETS_COLLECTION}"
