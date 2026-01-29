#!/usr/bin/env python3
"""
Backfill Voyage embeddings into the demo memory collection.

Targets:
  MEMORY_DB.MEMORY_COLLECTION (defaults: mcp_config.agent_memory)

Writes:
  EMBEDDING_FIELD (default: embedding_voyage_v4)

Idempotent:
- Only embeds documents where the embedding field is missing (or null) unless FORCE=1.
- This supports Pattern A: run it after your agent writes new memory docs.

Environment variables:
  MONGODB_URI
  VOYAGE_API_KEY                 preferred
  MDB_MCP_VOYAGE_API_KEY         fallback (same key used by mongodb-mcp-server)
  VOYAGE_MODEL                   default: voyage-4
  VOYAGE_OUTPUT_DIM              default: 1024
  EMBEDDING_FIELD                default: embedding_voyage_v4
  MEMORY_DB                      default: mcp_config
  MEMORY_COLLECTION              default: agent_memory
  BATCH_SIZE                     default: 32
  MAX_DOCS                       optional cap
  FORCE=1                        recompute even if embedding exists
  STORE_DERIVED_TEXT=1           store the derived embedding text (optional, default: 0)
  DERIVED_TEXT_FIELD             default: embedding_text_voyage_v4

Text composition (best effort):
- subject/title
- query/queryText
- summary/memory
- signals
- nextActions/next_actions
"""
from __future__ import annotations

import os
from typing import Any, Iterable

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection

import voyageai

try:
    from tqdm import tqdm
except Exception:
    tqdm = None  # type: ignore

load_dotenv()

DEFAULT_MODEL = "voyage-4"
DEFAULT_DIM = 1024
DEFAULT_EMBED_FIELD = "embedding_voyage_v4"
DEFAULT_MEM_DB = "mcp_config"
DEFAULT_MEM_COLL = "agent_memory"
DEFAULT_DERIVED_TEXT_FIELD = "embedding_text_voyage_v4"


def env(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if not v:
        raise SystemExit(f"Missing required env var: {name}")
    return v


def get_voyage_key() -> str:
    key = os.getenv("VOYAGE_API_KEY")
    if key:
        return key
    key = os.getenv("MDB_MCP_VOYAGE_API_KEY")
    if key:
        return key
    raise SystemExit("Missing Voyage API key. Set VOYAGE_API_KEY or MDB_MCP_VOYAGE_API_KEY in .env")


def batched(items: list[dict[str, Any]], batch_size: int) -> Iterable[list[dict[str, Any]]]:
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if x is not None and str(x).strip()]
    s = str(v).strip()
    return [s] if s else []


def build_text(doc: dict[str, Any]) -> str:
    parts: list[str] = []

    subject = (doc.get("subject") or doc.get("title") or "").strip()
    if subject:
        parts.append(f"Subject: {subject}")

    query = (doc.get("query") or doc.get("queryText") or "").strip()
    if query:
        parts.append(f"Query: {query}")

    # Some docs may use "summary"; others might use "memory"
    summary = (doc.get("summary") or doc.get("memory") or "").strip()
    if summary:
        parts.append(f"Summary: {summary}")

    signals = _as_list(doc.get("signals"))
    if signals:
        parts.append("Signals: " + ", ".join(signals))

    next_actions = _as_list(doc.get("nextActions") or doc.get("next_actions"))
    if next_actions:
        parts.append("Next actions: " + "; ".join(next_actions))

    if not parts:
        parts.append(str({k: v for k, v in doc.items() if k not in ("_id",)}))

    return "\n".join(parts).strip()


def main() -> None:
    mongo_uri = env("MONGODB_URI")
    voyage_key = get_voyage_key()
    model = os.getenv("VOYAGE_MODEL", DEFAULT_MODEL)
    out_dim = int(os.getenv("VOYAGE_OUTPUT_DIM", str(DEFAULT_DIM)))
    embed_field = os.getenv("EMBEDDING_FIELD", DEFAULT_EMBED_FIELD)

    mem_db = os.getenv("MEMORY_DB", DEFAULT_MEM_DB)
    mem_coll = os.getenv("MEMORY_COLLECTION", DEFAULT_MEM_COLL)

    batch_size = int(os.getenv("BATCH_SIZE", "32"))
    max_docs = os.getenv("MAX_DOCS")
    max_docs_i = int(max_docs) if max_docs else None
    force = os.getenv("FORCE", "0") == "1"

    store_text = os.getenv("STORE_DERIVED_TEXT", "0") == "1"
    derived_field = os.getenv("DERIVED_TEXT_FIELD", DEFAULT_DERIVED_TEXT_FIELD)

    client = MongoClient(mongo_uri)
    coll: Collection = client[mem_db][mem_coll]

    if force:
        query: dict[str, Any] = {}
    else:
        query = {"$or": [{embed_field: {"$exists": False}}, {embed_field: None}]}

    projection = {
        "_id": 1,
        "subject": 1,
        "title": 1,
        "query": 1,
        "queryText": 1,
        "summary": 1,
        "memory": 1,
        "signals": 1,
        "nextActions": 1,
        "next_actions": 1,
    }

    cursor = coll.find(query, projection=projection).batch_size(batch_size)

    docs: list[dict[str, Any]] = []
    for doc in cursor:
        docs.append(doc)
        if max_docs_i and len(docs) >= max_docs_i:
            break

    if not docs:
        print("Nothing to embed (all memory docs already have embeddings, or no docs present).")
        return

    print(f"Embedding {len(docs)} memory docs in {mem_db}.{mem_coll} using {model} (dim={out_dim}) -> {embed_field}")

    vclient = voyageai.Client(api_key=voyage_key)

    progress = tqdm(total=len(docs)) if tqdm else None
    updated = 0

    for chunk in batched(docs, batch_size):
        texts = [build_text(d) for d in chunk]
        ids = [d["_id"] for d in chunk]

        resp = vclient.embed(texts, model=model, output_dimension=out_dim)
        embeddings = resp.embeddings

        ops = []
        for _id, emb, txt in zip(ids, embeddings, texts):
            set_doc = {embed_field: emb}
            if store_text:
                set_doc[derived_field] = txt
            ops.append(UpdateOne({"_id": _id}, {"$set": set_doc}))

        res = coll.bulk_write(ops, ordered=False)
        updated += res.modified_count

        if progress:
            progress.update(len(chunk))

    if progress:
        progress.close()

    print(f"Done. Updated {updated} memory documents.")


if __name__ == "__main__":
    main()
