#!/usr/bin/env python3
"""
Add Voyage AI embeddings for the `plot` field in `sample_mflix.movies`.

Requirements:
  pip install pymongo python-dotenv voyageai

Environment variables (recommended to put in a .env file next to this script):
  MONGODB_URI=your mongodb+srv or standard URI
  VOYAGE_API_KEY=your voyage api key
  DB_NAME=sample_mflix             # optional, defaults to sample_mflix
  COLLECTION_NAME=movies           # optional, defaults to movies
  VOYAGE_MODEL=voyage-3.5          # optional, voyage-3.5 / voyage-3.5-lite / voyage-3-large / voyage-code-3
  EMBEDDING_DIM=1024               # optional, must match your Atlas Vector Search index dims
  BATCH_SIZE=128                   # optional, docs processed per batch
  DRY_RUN=false                    # optional, if "true", does not write to MongoDB

The script:
  - Ensures a Search index named `plot_embedding_index` exists (create if missing).
  - Batches through documents missing `plot_embedding`, computes embeddings for `plot`,
    and writes them to `plot_embedding` using bulk writes.
  - Skips docs without a non-empty `plot` field.
  - Safe to re-run; it only processes docs missing `plot_embedding`.
"""

import os
import sys
import time
from typing import List, Dict

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError
import voyageai

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")

if not MONGODB_URI:
    print("ERROR: MONGODB_URI not set. Set it in your environment or .env file.", file=sys.stderr)
    sys.exit(1)
if not VOYAGE_API_KEY:
    print("ERROR: VOYAGE_API_KEY not set. Set it in your environment or .env file.", file=sys.stderr)
    sys.exit(1)

DB_NAME = os.getenv("DB_NAME", "sample_mflix")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "movies")
VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-3.5")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "128"))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# Connect clients
client = voyageai.Client(api_key=VOYAGE_API_KEY)
mongo = MongoClient(
    os.getenv("MONGODB_URI"),
    tls=True,
    tlsCertificateKeyFile=os.getenv("MONGODB_CERT")
)
coll = mongo[DB_NAME][COLLECTION_NAME]

def ensure_vector_index():
    """
    Create/ensure an Atlas Vector Search index for plot_embedding with the right dimension.
    Uses name: plot_embedding_index
    """
    try:
        # Check if exists
        existing = mongo[DB_NAME].command({
            "listSearchIndexes": COLLECTION_NAME,
            "name": "plot_embedding_index"
        }).get("indexes", [])
    except PyMongoError:
        # Older drivers/servers may not support listSearchIndexes via command; ignore and try to create
        existing = []

    if existing:
        # Optionally verify dims/similarity, but we'll skip strict checks
        return
    
    index_def = {
        "name": "plot_embedding_index",
        "type": "vectorSearch",  
        "definition": {
            "fields": [
                {
                    "type": "vector",
                    "path": "plot_embedding",
                    "numDimensions": EMBEDDING_DIM,
                    "similarity": "cosine"
                },
                {
                    "type": "filter",
                    "path": "year"
                }
            ]
        }
    }

    try:
        mongo[DB_NAME][COLLECTION_NAME].create_search_index(index_def)
        print(f"Created Vector Search index 'plot_embedding_index' with dims={EMBEDDING_DIM}")
    except PyMongoError as e:
        # Non-fatal: user may lack permissions, or index already exists
        print(f"WARN: Could not create vector index automatically: {e}", file=sys.stderr)

def batched(iterable, n):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= n:
            yield batch
            batch = []
    if batch:
        yield batch

def fetch_docs_to_process(limit: int = BATCH_SIZE):
    """
    Query only docs that need embeddings and have a non-empty plot string.
    """
    return coll.find(
        {
            "plot_embedding": {"$exists": False},
            "plot": {"$type": "string", "$ne": ""}
        },
        {
            "_id": 1,
            "plot": 1
        },
        no_cursor_timeout=True
    ).batch_size(BATCH_SIZE)

def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Call Voyage to embed a list of strings.
    """
    for _ in range(5):  # simple retry with backoff
        try:
            resp = client.embed(
                texts=texts,
                model=VOYAGE_MODEL,
                input_type="document",
                truncation=True,
                output_dimension=EMBEDDING_DIM
            )
            # voyageai returns `.embeddings` on response
            return resp.embeddings
        except voyageai.error.RateLimitError as e:  # type: ignore[attr-defined]
            print(f"Rate limited, retrying in 5s: {e}", file=sys.stderr)
            time.sleep(5)
        except Exception as e:
            print(f"Embed error (no retry): {e}", file=sys.stderr)
            raise
    raise RuntimeError("Exceeded retries for embed_texts")

def main():
    # ensure_vector_index()

    cursor = fetch_docs_to_process()
    total_updates = 0
    try:
        while True:
            batch_docs = [d for _, d in zip(range(BATCH_SIZE), cursor)]
            if not batch_docs:
                break

            texts = [d["plot"] for d in batch_docs]
            try:
                vectors = embed_texts(texts)
            except Exception:
                # Skip this batch on error
                continue

            ops = []
            for doc, vec in zip(batch_docs, vectors):
                ops.append(
                    UpdateOne({"_id": doc["_id"]}, {"$set": {"plot_embedding": vec}})
                )

            if DRY_RUN:
                print(f"DRY_RUN: would update {len(ops)} docs")
            elif ops:
                result = coll.bulk_write(ops, ordered=False)
                total_updates += (result.upserted_count or 0) + (result.modified_count or 0)
                print(f"Updated {result.modified_count} docs in this batch; total so far: {total_updates}")

    finally:
        cursor.close()

    print(f"Done. Total documents updated with plot_embedding: {total_updates}")

    ensure_vector_index()

if __name__ == "__main__":
    main()
