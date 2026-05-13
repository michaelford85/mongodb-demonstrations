import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
import voyageai

load_dotenv(Path(__file__).parent.parent / ".env")

_mongo_client = None
_voyage_client = None


def get_mongo() -> MongoClient:
    global _mongo_client
    if _mongo_client is None:
        uri = os.getenv("MONGODB_URI")
        cert = os.getenv("MONGODB_CERT")
        if cert:
            _mongo_client = MongoClient(uri, tls=True, tlsCertificateKeyFile=cert)
        else:
            _mongo_client = MongoClient(uri)
    return _mongo_client


def get_voyage() -> voyageai.Client:
    global _voyage_client
    if _voyage_client is None:
        _voyage_client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
    return _voyage_client


def get_collection():
    mongo = get_mongo()
    db_name = os.getenv("DB_NAME", "ecommerce_demo")
    coll_name = os.getenv("COLLECTION_NAME", "products")
    return mongo[db_name][coll_name]


def get_collection_name() -> str:
    return os.getenv("COLLECTION_NAME", "products")


VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-3.5")
VOYAGE_RERANK_MODEL = os.getenv("VOYAGE_RERANK_MODEL", "voyage-rerank-2")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
QUERY_LIMIT = int(os.getenv("QUERY_LIMIT", "10"))
