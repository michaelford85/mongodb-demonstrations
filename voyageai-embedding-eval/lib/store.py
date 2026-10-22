"""Vector stores: Atlas Vector Search (real) and an in-memory twin (dry run).

Each model gets its OWN collection and its OWN vector index, so vectors from
different models are never mixed in one field. The index dimension is taken
from a real embedding, never assumed, and a mismatch with an existing index is
an error rather than something we try to reshape.
"""
from __future__ import annotations

import time

import numpy as np

from lib.config import EvalError

VECTOR_FIELD = "embedding"
SIMILARITY = "cosine"
NUM_CANDIDATES_FACTOR = 20     # numCandidates = limit * factor (min 100)
INSERT_BATCH = 100             # 100 x 3072 doubles stays well under the 16 MB document-batch limit


class StoreError(EvalError):
    pass


def index_definition(num_dimensions: int) -> dict:
    """The Atlas Vector Search index definition this demo creates."""
    return {"fields": [{"type": "vector", "path": VECTOR_FIELD,
                        "numDimensions": num_dimensions, "similarity": SIMILARITY}]}


def num_candidates_for(limit: int) -> int:
    return min(max(limit * NUM_CANDIDATES_FACTOR, 100), 10000)


def vector_search_pipeline(index_name: str, query_vector, limit: int) -> list[dict]:
    """The exact aggregation sent to Atlas for one query."""
    return [
        {"$vectorSearch": {
            "index": index_name,
            "path": VECTOR_FIELD,
            "queryVector": query_vector,
            "numCandidates": num_candidates_for(limit),
            "limit": limit,
        }},
        {"$project": {"_id": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]


class AtlasStore:
    def __init__(self, client, db_name: str):
        self.db = client[db_name]

    def prepare(self, collection: str, index_name: str, dims: int) -> None:
        from pymongo.operations import SearchIndexModel
        from pymongo.errors import PyMongoError
        try:
            if collection not in self.db.list_collection_names():
                self.db.create_collection(collection)
            coll = self.db[collection]
            existing = list(coll.list_search_indexes(index_name))
            if existing:
                fields = (existing[0].get("latestDefinition") or existing[0].get("definition") or {}).get("fields", [])
                have = next((f.get("numDimensions") for f in fields if f.get("path") == VECTOR_FIELD), None)
                if have != dims:
                    raise StoreError(
                        f"Index '{index_name}' on '{collection}' has numDimensions={have}, but this model "
                        f"produces {dims}-dimensional vectors. Run scripts/cleanup.py and try again."
                    )
                return
            coll.create_search_index(SearchIndexModel(
                definition=index_definition(dims), name=index_name, type="vectorSearch"))
        except PyMongoError as exc:
            raise StoreError(_mongo_hint(exc)) from None

    def existing_ids(self, collection: str) -> set[str]:
        return {d["_id"] for d in self.db[collection].find({}, {"_id": 1})}

    def insert(self, collection: str, docs: list[dict]) -> None:
        from pymongo.errors import PyMongoError
        try:
            for i in range(0, len(docs), INSERT_BATCH):
                self.db[collection].insert_many(docs[i:i + INSERT_BATCH], ordered=False)
        except PyMongoError as exc:
            raise StoreError(_mongo_hint(exc)) from None

    def wait_until_queryable(self, collection: str, index_name: str, timeout: float = 300,
                             on_wait=None) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            idx = next(iter(self.db[collection].list_search_indexes(index_name)), None)
            if idx and idx.get("queryable"):
                return
            if idx and idx.get("status") == "FAILED":
                raise StoreError(f"Index '{index_name}' build FAILED in Atlas. Check the index in the Atlas UI.")
            if on_wait:
                on_wait(idx.get("status", "PENDING") if idx else "PENDING")
            time.sleep(3)
        raise StoreError(f"Index '{index_name}' was not queryable after {int(timeout)}s. "
                         "Search index builds can take a minute or two; try again shortly.")

    def search(self, collection: str, index_name: str, vector, limit: int) -> list[str]:
        from pymongo.errors import PyMongoError
        try:
            rows = self.db[collection].aggregate(vector_search_pipeline(index_name, vector, limit))
            return [r["_id"] for r in rows]
        except PyMongoError as exc:
            raise StoreError(_mongo_hint(exc)) from None

    def drop(self, collection: str) -> None:
        self.db[collection].drop()   # dropping a collection also removes its search indexes


class MemoryStore:
    """Same interface as AtlasStore; exact cosine search in NumPy (dry run only)."""

    def __init__(self):
        self.data: dict[str, dict[str, list[float]]] = {}

    def prepare(self, collection, index_name, dims):
        self.data.setdefault(collection, {})

    def existing_ids(self, collection):
        return set(self.data.get(collection, {}))

    def insert(self, collection, docs):
        for d in docs:
            self.data[collection][d["_id"]] = d[VECTOR_FIELD]

    def wait_until_queryable(self, collection, index_name, timeout=0, on_wait=None):
        return

    def search(self, collection, index_name, vector, limit):
        ids = list(self.data[collection])
        mat = np.array([self.data[collection][i] for i in ids])
        q = np.array(vector)
        sims = mat @ q / ((np.linalg.norm(mat, axis=1) * np.linalg.norm(q)) + 1e-12)
        order = np.argsort(-sims, kind="stable")[:limit]
        return [ids[i] for i in order]

    def drop(self, collection):
        self.data.pop(collection, None)


def _mongo_hint(exc: Exception) -> str:
    """Actionable text without echoing the connection string."""
    name = type(exc).__name__
    text = str(exc)
    if "AuthenticationFailed" in name or "Authentication failed" in text:
        return "Atlas authentication failed. Check the username/password in MONGODB_URI."
    if "ServerSelectionTimeout" in name:
        return ("Could not reach the Atlas cluster. Check that your IP is on the Atlas access list "
                "and that the cluster is running.")
    if "SearchNotEnabled" in text or "vectorSearch" in text and "not supported" in text.lower():
        return "This cluster does not support Atlas Vector Search (an M0 or newer Atlas cluster is required)."
    if "maximum number" in text.lower() and "index" in text.lower():
        return ("Atlas refused to create another search index (tier limit reached; M0 allows 3). "
                "Run scripts/cleanup.py to remove old demo indexes.")
    return f"Atlas error ({name}): {text[:300]}"
