"""Shared MongoDB connection and lab configuration.

Every value here is driven by .env so the GUI, the setup scripts, and the
mongosh snippets in the README all agree on the same namespace and index
names. Change a name in one place (.env) and the whole lab stays in sync.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).parent.parent / ".env")

_client = None
_voyage_client = None

# ── Namespace ───────────────────────────────────────────────────────────────
DB_NAME = os.getenv("DB_NAME", "hybrid_search_lab")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "movies")

# ── Index names ─────────────────────────────────────────────────────────────
VECTOR_INDEX = os.getenv("VECTOR_INDEX", "movies_vector_index")
TEXT_INDEX = os.getenv("TEXT_INDEX", "movies_text_index")

# ── Automated Embedding ─────────────────────────────────────────────────────
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "voyage-4")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))

# ── App settings ────────────────────────────────────────────────────────────
QUERY_LIMIT = int(os.getenv("QUERY_LIMIT", "10"))

# The single text field that is BOTH BM25-indexed and autoEmbed-indexed.
# Keeping keyword and semantic search on the same field makes the hybrid
# comparison honest — both legs see the same words.
SEARCH_FIELD = "plot"

# ── Reranking (optional — only the rerank strategy needs these) ───────────────
# A Voyage AI cross-encoder re-scores the hybrid candidates client-side. This is
# the one strategy that is NOT reproducible in mongosh, so it stays fully
# optional: the other three run without voyageai installed or a key configured.
VOYAGE_RERANK_MODEL = os.getenv("VOYAGE_RERANK_MODEL", "voyage-rerank-2")


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


def get_collection():
    return get_client()[DB_NAME][COLLECTION_NAME]


def get_voyage():
    """Lazily build a Voyage AI client for the rerank strategy.

    voyageai is an optional dependency imported only here, so the keyword,
    semantic, and hybrid strategies run without it installed or a key set.
    """
    global _voyage_client
    if _voyage_client is None:
        api_key = os.getenv("VOYAGE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "VOYAGE_API_KEY is not set. Only the rerank strategy needs it; "
                "the keyword, semantic, and hybrid strategies do not."
            )
        try:
            import voyageai
        except ImportError as exc:
            raise RuntimeError(
                "voyageai is not installed. Run: pip install -r requirements.txt"
            ) from exc
        _voyage_client = voyageai.Client(api_key=api_key)
    return _voyage_client
