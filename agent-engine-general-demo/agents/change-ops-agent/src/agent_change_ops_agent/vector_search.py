"""Optional semantic retrieval over synthetic change notes.

Uses MongoDB Atlas Automated Embedding: the Vector Search index declares an
``autoEmbed`` field, so Atlas generates and manages embeddings with a Voyage AI
model at index time and embeds the plain-text query at query time. No client
Voyage API key is required for this path.

This module only READS. Index creation is a separate, explicit, demo-scoped
setup step (scripts/create_vector_index.py). When the index or cluster is
unavailable, callers fall back to deterministic keyword search.

Verified against the MongoDB Vector Search "Automated Embedding" docs:
index field {"type": "autoEmbed", "modality": "text", "path": ..., "model": ...}
and $vectorSearch with a TEXT "query" plus optional "model".
"""

import logging

logger = logging.getLogger(__name__)

# Atlas Automated Embedding model (current docs list voyage-4 as the
# recommended balanced general-text model).
EMBEDDING_MODEL = "voyage-4"
VECTOR_INDEX_NAME = "change_notes_autoembed_index"
EMBEDDING_PATH = "note_text"


def index_definition() -> dict:
    """Vector Search index definition for the demo change_notes collection.

    Scoped entirely to this demo's collection. Uses the autoEmbed field type
    so Atlas manages embeddings; no vectors are stored in the demo collection.
    """
    return {
        "name": VECTOR_INDEX_NAME,
        "type": "vectorSearch",
        "definition": {
            "fields": [
                {
                    "type": "autoEmbed",
                    "modality": "text",
                    "path": EMBEDDING_PATH,
                    "model": EMBEDDING_MODEL,
                },
                {"type": "filter", "path": "workspace_id"},
            ]
        },
    }


def vector_search_notes(client, database: str, collection_name: str, query: str, limit: int = 3) -> list:
    """Run one $vectorSearch (text query) against the demo notes collection."""
    collection = client[database][collection_name]
    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_NAME,
                "path": EMBEDDING_PATH,
                "query": query,
                "filter": {"workspace_id": {"$eq": "demo_workspace_001"}},
                "limit": limit,
            }
        },
        {
            "$project": {
                "_id": 0,
                "note_id": 1,
                "workspace_id": 1,
                "title": 1,
                "note_text": 1,
                "related_service_id": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    return [dict(doc) for doc in collection.aggregate(pipeline)]
