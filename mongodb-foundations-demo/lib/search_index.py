"""Create and inspect the two Atlas Search indexes the sections rely on.

  1. A Vector Search index of type `autoEmbed` on the chunk text. Atlas
     generates the embeddings itself — at index time AND at query time — using
     the Voyage AI model in `.env`, so neither the GUI nor mongosh ever computes
     a vector. Semantic and hybrid queries take plain natural-language text.

  2. An Atlas Search (BM25) index on the same text field for keyword search.

Both index names are fixed constants so the README's mongosh snippets run
verbatim. Index builds are asynchronous — allow a minute or two after creation.
"""

from __future__ import annotations

from pymongo.errors import OperationFailure
from pymongo.operations import SearchIndexModel

from lib.search_config import (EMBEDDING_DIM, EMBEDDING_MODEL, SEARCH_FIELD,
                               TEXT_INDEX, VECTOR_INDEX, get_knowledge)

# autoEmbed vector index: Atlas owns the embeddings on both sides of the query.
# The two filter fields let the RAG section pre-filter retrieval by source.
VECTOR_DEFINITION = {
    "fields": [
        {"type": "autoEmbed", "modality": "text", "path": SEARCH_FIELD,
         "model": EMBEDDING_MODEL, "numDimensions": EMBEDDING_DIM,
         "similarity": "cosine"},
        {"type": "filter", "path": "source_type"},
        {"type": "filter", "path": "doc_id"},
    ]
}

# BM25 keyword index on the same text, plus the title and section for context.
TEXT_DEFINITION = {
    "mappings": {
        "dynamic": False,
        "fields": {
            SEARCH_FIELD: {"type": "string", "analyzer": "lucene.english"},
            "doc_title": {"type": "string"},
            "section": {"type": "string"},
        },
    }
}

SEARCH_INDEXES = {
    VECTOR_INDEX: ("vectorSearch", VECTOR_DEFINITION),
    TEXT_INDEX: ("search", TEXT_DEFINITION),
}


def _existing(coll) -> dict:
    try:
        return {ix["name"]: ix for ix in coll.list_search_indexes()}
    except OperationFailure:
        return {}


def create_search_indexes(coll=None) -> list:
    """Create both search indexes. Idempotent. Returns the names created now."""
    coll = get_knowledge() if coll is None else coll
    existing = set(_existing(coll))
    created = []
    for name, (index_type, definition) in SEARCH_INDEXES.items():
        if name in existing:
            continue
        coll.create_search_index(
            SearchIndexModel(name=name, type=index_type, definition=definition))
        created.append(name)
    return created


def search_index_status(coll=None) -> list:
    """Presenter-friendly status per search index: READY / building / missing."""
    coll = get_knowledge() if coll is None else coll
    existing = _existing(coll)
    rows = []
    for name in SEARCH_INDEXES:
        ix = existing.get(name)
        if not ix:
            rows.append({"index": name, "status": "MISSING", "queryable": False})
            continue
        queryable = bool(ix.get("queryable", False))
        rows.append({
            "index": name,
            "status": "READY" if queryable else ix.get("status", "BUILDING"),
            "queryable": queryable,
        })
    return rows


def missing_search_indexes(coll=None) -> list:
    """Names of search indexes that do not exist yet."""
    coll = get_knowledge() if coll is None else coll
    existing = set(_existing(coll))
    return [name for name in SEARCH_INDEXES if name not in existing]


def indexes_ready(coll=None) -> bool:
    """True only when both search indexes exist and are queryable."""
    return all(row["queryable"] for row in search_index_status(coll))


def drop_search_indexes(coll=None) -> list:
    """Drop both search indexes if present. Used by resets and teardown."""
    coll = get_knowledge() if coll is None else coll
    existing = set(_existing(coll))
    dropped = []
    for name in SEARCH_INDEXES:
        if name in existing:
            coll.drop_search_index(name)
            dropped.append(name)
    return dropped
