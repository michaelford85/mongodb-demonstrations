"""Seed and reset the chunked-documents collection for Search & RAG.

Guarded like the core seed: it asserts the target database is the demo database
and only ever touches the single `knowledge_chunks` collection. Nothing runs
automatically — the app calls it from an explicit, confirmed action and the
`seed_search.py` script calls it from the command line.
"""

from __future__ import annotations

from pymongo.database import Database

from lib.mongo_client import DB_NAME, get_db
from lib.search_config import KNOWLEDGE
from lib.search_data import build_chunks


def _guard(db: Database) -> None:
    """Refuse to run a destructive operation outside the demo database."""
    if db.name != DB_NAME:
        raise RuntimeError(
            "Refusing to modify database '{}' — this demo only owns '{}'."
            .format(db.name, DB_NAME))


def seed_knowledge(db: Database = None) -> dict:
    """Drop and rebuild `knowledge_chunks` from the deterministic chunker.

    Returns the chunk count and the number of distinct source documents, for
    display. The Atlas Search indexes are created separately — Automated
    Embedding then embeds every chunk as soon as it is inserted.
    """
    db = get_db() if db is None else db
    _guard(db)
    chunks = build_chunks()
    db[KNOWLEDGE].drop()
    db[KNOWLEDGE].insert_many(chunks)
    doc_ids = {c["doc_id"] for c in chunks}
    return {"chunks": len(chunks), "documents": len(doc_ids)}


def drop_knowledge(db: Database = None) -> str:
    """Drop only the chunked-documents collection. Used by resets and teardown."""
    db = get_db() if db is None else db
    _guard(db)
    db[KNOWLEDGE].drop()
    return KNOWLEDGE
