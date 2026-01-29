#!/usr/bin/env python3
"""
Backfill Voyage embeddings into sample_mflix.comments.embedding_voyage_v4.

Safe to re-run:
- Only processes documents where the embedding field is missing (or null) unless FORCE=1.

Environment variables:
  MONGODB_URI                 MongoDB connection string
  VOYAGE_API_KEY              Voyage API key (preferred)
  MDB_MCP_VOYAGE_API_KEY      Fallback Voyage API key (used by mongodb-mcp-server)
  VOYAGE_MODEL                default: voyage-4
  VOYAGE_OUTPUT_DIM           default: 1024
  EMBEDDING_FIELD             default: embedding_voyage_v4
  BATCH_SIZE                  default: 64
  MAX_DOCS                    optional cap for demos (highly recommended)
  FORCE=1                     recompute even if embedding exists
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


def env(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if not v:
        raise SystemExit(f"Missing required env var: {name}")
    return v


def get_voyage_key() -> str:
    """Prefer VOYAGE_API_KEY, fall back to MDB_MCP_VOYAGE_API_KEY."""
    key = os.getenv("VOYAGE_API_KEY")
    if key:
        return key
    key = os.getenv("MDB_MCP_VOYAGE_API_KEY")
    if key:
        return key
    raise SystemExit(
        "Missing Voyage API key. Set VOYAGE_API_KEY or MDB_MCP_VOYAGE_API_KEY in .env"
    )


def batched(items: list[dict[str, Any]], batch_size: int) -> Iterable[list[dict[str, Any]]]:
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def get_text(doc: dict[str, Any]) -> str:
    return (doc.get("text") or "").strip()


def main() -> None:
    mongo_uri = env("MONGODB_URI")
    voyage_key = get_voyage_key()
    model = os.getenv("VOYAGE_MODEL", DEFAULT_MODEL)
    out_dim = int(os.getenv("VOYAGE_OUTPUT_DIM", str(DEFAULT_DIM)))
    embed_field = os.getenv("EMBEDDING_FIELD", DEFAULT_EMBED_FIELD)

    batch_size = int(os.getenv("BATCH_SIZE", "64"))
    max_docs = os.getenv("MAX_DOCS")
    max_docs_i = int(max_docs) if max_docs else None
    force = os.getenv("FORCE", "0") == "1"

    client = MongoClient(mongo_uri)
    coll: Collection = client["sample_mflix"]["comments"]

    if force:
        query = {"text": {"$type": "string", "$ne": ""}}
    else:
        query = {
            "text": {"$type": "string", "$ne": ""},
            "$or": [{embed_field: {"$exists": False}}, {embed_field: None}],
        }

    projection = {"_id": 1, "text": 1}
    cursor = coll.find(query, projection=projection).batch_size(batch_size)

    docs: list[dict[str, Any]] = []
    for doc in cursor:
        docs.append(doc)
        if max_docs_i and len(docs) >= max_docs_i:
            break

    if not docs:
        print("Nothing to embed (all docs already have embeddings, or no matching docs).")  # noqa: T201
        return

    print(  # noqa: T201
        f"Embedding {len(docs)} comment documents using {model} (dim={out_dim}) -> field '{embed_field}'"
    )

    vclient = voyageai.Client(api_key=voyage_key)

    progress = tqdm(total=len(docs)) if tqdm else None
    updated = 0

    for chunk in batched(docs, batch_size):
        texts = [get_text(d) for d in chunk]
        ids = [d["_id"] for d, t in zip(chunk, texts) if t]
        texts = [t for t in texts if t]

        if not texts:
            if progress:
                progress.update(len(chunk))
            continue

        resp = vclient.embed(texts, model=model, output_dimension=out_dim)
        embeddings = resp.embeddings  # list[list[float]]

        ops = [UpdateOne({"_id": _id}, {"$set": {embed_field: emb}}) for _id, emb in zip(ids, embeddings)]

        if ops:
            res = coll.bulk_write(ops, ordered=False)
            updated += res.modified_count

        if progress:
            progress.update(len(chunk))

    if progress:
        progress.close()

    print(f"Done. Updated {updated} documents.")  # noqa: T201


if __name__ == "__main__":
    main()
