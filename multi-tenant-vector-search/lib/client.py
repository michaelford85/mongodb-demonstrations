"""Shared MongoDB connection, Voyage AI client, and demo configuration.

Every value here is driven by .env so the setup scripts, the router, and the
mongosh snippets in the README all agree on the same namespace, index names,
and view names. Change a name in one place (.env) and the whole demo stays
in sync.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).parent.parent / ".env")

_client = None
_voyage_client = None

# ── Namespace ───────────────────────────────────────────────────────────────
DB_NAME = os.getenv("DB_NAME", "multi_tenant_vector_search")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "documents")

# ── Index / View names ──────────────────────────────────────────────────────
FLAT_INDEX = os.getenv("FLAT_INDEX", "shared_flat_index")
HNSW_INDEX = os.getenv("HNSW_INDEX", "tenant_hnsw_index")
VIEW_PREFIX = os.getenv("VIEW_PREFIX", "tenant_view_")

# ── Embeddings ──────────────────────────────────────────────────────────────
VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-3.5")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "128"))

# ── Dataset / query settings ────────────────────────────────────────────────
PROFILE = os.getenv("PROFILE", "demo")
QUERY_LIMIT = int(os.getenv("QUERY_LIMIT", "10"))

# The single text field that is embedded and searched. Keeping the whole demo
# on one field makes the flat-vs-HNSW comparison honest — both regimes see the
# same vectors, only the index structure differs.
TEXT_FIELD = "text"
EMBEDDING_FIELD = "embedding"
TENANT_FIELD = "tenant_id"


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


def get_collection():
    return get_db()[COLLECTION_NAME]


def view_name(tenant_id: str) -> str:
    """The view namespace hosting a large tenant's dedicated HNSW index."""
    return f"{VIEW_PREFIX}{tenant_id}"


def get_voyage():
    """Lazily build a Voyage AI client.

    voyageai is imported only here so the demo runs end-to-end with
    --fake-embeddings and no key installed or configured.
    """
    global _voyage_client
    if _voyage_client is None:
        api_key = os.getenv("VOYAGE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "VOYAGE_API_KEY is not set. Set it, or pass --fake-embeddings "
                "to generate deterministic offline vectors instead."
            )
        try:
            import voyageai
        except ImportError as exc:
            raise RuntimeError(
                "voyageai is not installed. Run: pip install -r requirements.txt"
            ) from exc
        _voyage_client = voyageai.Client(api_key=api_key)
    return _voyage_client
