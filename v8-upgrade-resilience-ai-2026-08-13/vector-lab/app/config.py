"""Environment-driven configuration for the knowledge base search lab.

Nothing here provisions a cluster — see ../../atlas-cluster-provisioning. Both
secrets (the connection string and the embedding provider key) come from the
environment; neither is ever written to disk by this lab.

The embedding provider is pluggable so the lab can run in three ways:

  * EMBEDDING_PROVIDER=voyage   real embeddings + real reranking
  * EMBEDDING_PROVIDER=openai   real embeddings, reranking falls back to offline
  * EMBEDDING_PROVIDER=offline  deterministic hash vectors, no key, no network
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


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


# ── Namespace ───────────────────────────────────────────────────────────────
DB_NAME = os.getenv("DB_NAME", "vector_lab")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "kb_articles")

TEXT_INDEX = os.getenv("TEXT_INDEX", "kb_text_index")
VECTOR_INDEX = os.getenv("VECTOR_INDEX", "kb_vector_index")

# Fields the search paths read. `body` is what gets embedded and reranked.
TITLE_FIELD = "title"
BODY_FIELD = "body"
EMBEDDING_FIELD = "embedding"

# ── Embedding provider ──────────────────────────────────────────────────────
# "offline" needs no key at all, which keeps the lab runnable in a workshop
# where handing out provider keys is not practical.
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "offline").strip().lower()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "voyage-3.5")
EMBEDDING_DIM = _int("EMBEDDING_DIM", 1024)
RERANK_MODEL = os.getenv("RERANK_MODEL", "rerank-2")
EMBEDDING_BATCH_SIZE = _int("EMBEDDING_BATCH_SIZE", 64)

# ── Search behaviour ────────────────────────────────────────────────────────
RESULT_LIMIT = _int("RESULT_LIMIT", 8)
# The reranker only improves on the vector order if it is given more to work
# with than it returns, so oversample the candidate pool first.
RERANK_CANDIDATES = _int("RERANK_CANDIDATES", 40)
NUM_CANDIDATES_MULTIPLIER = _int("NUM_CANDIDATES_MULTIPLIER", 15)
SNIPPET_CHARS = _int("SNIPPET_CHARS", 220)

# ── Service ─────────────────────────────────────────────────────────────────
HOST = os.getenv("HOST", "127.0.0.1")
PORT = _int("PORT", 8001)
SHOW_PIPELINE = _bool("SHOW_PIPELINE", True)

DATA_FILE = Path(__file__).parent.parent / "data" / "knowledge_base.json"

_client = None


def embedding_api_key() -> str:
    """The provider key, or an empty string when running offline."""
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
        opts = {"appname": "vector-lab"}
        cert = os.getenv("MONGODB_CERT")
        if cert:
            opts.update(tls=True, tlsCertificateKeyFile=cert)
        _client = MongoClient(uri, **opts)
    return _client


def get_articles():
    return get_client()[DB_NAME][COLLECTION_NAME]


def namespace() -> str:
    return f"{DB_NAME}.{COLLECTION_NAME}"
