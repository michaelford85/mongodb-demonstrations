#!/usr/bin/env python3
"""
Backfill Voyage embeddings into sample_mflix.movies.embedding_voyage_v4.

This script embeds a derived text field:
  title + genres + fullplot

Safe to re-run:
- Only processes documents where the embedding field is missing (or null) unless FORCE=1.

Environment variables:
  MONGODB_URI                 MongoDB connection string
  VOYAGE_API_KEY              Voyage API key (preferred)
  MDB_MCP_VOYAGE_API_KEY      Fallback Voyage API key (used by mongodb-mcp-server)
  VOYAGE_MODEL                default: voyage-4
  VOYAGE_OUTPUT_DIM           default: 1024
  EMBEDDING_FIELD             default: embedding_voyage_v4
  BATCH_SIZE                  default: 32   (movies fullplot can be large)
  MAX_DOCS                    optional cap for demos
  FORCE=1                     recompute even if embedding exists
  STORE_DERIVED_TEXT=1        also store derived text in movie doc (optional, default: 0)
  DERIVED_TEXT_FIELD          default: embedding_text_voyage_v4
"""
from __future__ import annotations

import os
from typing import Any, Iterable

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection
from pymongo import UpdateOne

import voyageai

try:
    from tqdm import tqdm
except Exception:
    tqdm = None  # type: ignore

load_dotenv()

DEFAULT_MODEL = "voyage-4"
DEFAULT_DIM = 1024
DEFAULT_EMBED_FIELD = "embedding_voyage_v4"
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


def build_text(doc: dict[str, Any]) -> str:
    title = (doc.get("title") or "").strip()
    genres = doc.get("genres") or []
    if isinstance(genres, list):
        genres_str = ", ".join([str(g) for g in genres if g])
    else:
        genres_str = str(genres)
    fullplot = (doc.get("fullplot") or "").strip()

    parts = []
    if title:
        parts.append(f"Title: {title}")
    if genres_str:
        parts.append(f"Genres: {genres_str}")
    if fullplot:
        parts.append(f"Plot: {fullplot}")
    return "\n".join(parts).strip()


def main() -> None:
    mongo_uri = env("MONGODB_URI")
    voyage_key = get_voyage_key()
    model = os.getenv("VOYAGE_MODEL", DEFAULT_MODEL)
    out_dim = int(os.getenv("VOYAGE_OUTPUT_DIM", str(DEFAULT_DIM)))
    embed_field = os.getenv("EMBEDDING_FIELD", DEFAULT_EMBED_FIELD)

    batch_size = int(os.getenv("BATCH_SIZE", "32"))
    max_docs = os.getenv("MAX_DOCS")
    max_docs_i = int(max_docs) if max_docs else None
    force = os.getenv("FORCE", "0") == "1"

    store_text = os.getenv("STORE_DERIVED_TEXT", "0") == "1"
    derived_field = os.getenv("DERIVED_TEXT_FIELD", DEFAULT_DERIVED_TEXT_FIELD)

    client = MongoClient(mongo_uri)
    coll: Collection = client["sample_mflix"]["movies"]

    # Keep query conservative: ensure some text exists to embed.
    base_query: dict[str, Any] = {
        "$or": [{"fullplot": {"$type": "string", "$ne": ""}}, {"title": {"$type": "string", "$ne": ""}}]
    }
    if force:
        query = base_query
    else:
        query = {**base_query, "$or": [*base_query["$or"], {embed_field: {"$exists": False}}, {embed_field: None}]}
        # The merge above isn't perfect logic; instead, keep it explicit:
        query = {
            **base_query,
            "$and": [
                base_query,
                {"$or": [{embed_field: {"$exists": False}}, {embed_field: None}]},
            ],
        }

    projection = {"_id": 1, "title": 1, "genres": 1, "fullplot": 1}
    cursor = coll.find(query, projection=projection).batch_size(batch_size)

    docs: list[dict[str, Any]] = []
    for doc in cursor:
        docs.append(doc)
        if max_docs_i and len(docs) >= max_docs_i:
            break

    if not docs:
        print("Nothing to embed (all docs already have embeddings, or no matching docs).")
        return

    print(f"Embedding {len(docs)} movie documents using {model} (dim={out_dim}) -> field '{embed_field}'")
    vclient = voyageai.Client(api_key=voyage_key)

    progress = tqdm(total=len(docs)) if tqdm else None
    updated = 0

    for chunk in batched(docs, batch_size):
        texts = [build_text(d) for d in chunk]
        ids = [d["_id"] for d, t in zip(chunk, texts) if t]
        texts = [t for t in texts if t]

        if not texts:
            if progress:
                progress.update(len(chunk))
            continue

        resp = vclient.embed(texts, model=model, output_dimension=out_dim)
        embeddings = resp.embeddings

        ops = []
        for _id, emb, txt in zip(ids, embeddings, texts):
            update_doc = {"$set": {embed_field: emb}}
            if store_text:
                update_doc["$set"][derived_field] = txt
            ops.append(UpdateOne({"_id": _id}, update_doc))
            

        if ops:
            res = coll.bulk_write(ops, ordered=False)
            updated += res.modified_count

        if progress:
            progress.update(len(chunk))

    if progress:
        progress.close()

    print(f"Done. Updated {updated} documents.")


if __name__ == "__main__":
    main()
