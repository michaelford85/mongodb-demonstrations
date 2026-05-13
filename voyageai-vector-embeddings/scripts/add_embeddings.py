#!/usr/bin/env python3
"""
Generate VoyageAI embeddings for all products missing an `embedding` field.

Usage:
    python scripts/add_embeddings.py [--dry-run]

The embedding text is: title + features + description (concatenated).
Safe to re-run — only processes documents that are missing the `embedding` field.

Requires: pip install pymongo python-dotenv voyageai
"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError
import voyageai

load_dotenv(Path(__file__).parent.parent / ".env")

VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-3.5")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "128"))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"


def build_embed_text(doc: dict) -> str:
    parts = [
        doc.get("title", ""),
        " ".join(doc.get("features") or []),
        doc.get("description", ""),
    ]
    return " ".join(p for p in parts if p).strip()


def embed_batch(client: voyageai.Client, texts: list[str]) -> list[list[float]]:
    for attempt in range(5):
        try:
            resp = client.embed(
                texts=texts,
                model=VOYAGE_MODEL,
                input_type="document",
                truncation=True,
                output_dimension=EMBEDDING_DIM,
            )
            return resp.embeddings
        except Exception as e:
            if "rate" in str(e).lower() and attempt < 4:
                wait = 2 ** attempt * 5
                print(f"  Rate limited, retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Exceeded retries")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Add VoyageAI embeddings to products")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    dry_run = DRY_RUN or args.dry_run

    uri = os.getenv("MONGODB_URI")
    cert = os.getenv("MONGODB_CERT")
    db_name = os.getenv("DB_NAME", "ecommerce_demo")
    coll_name = os.getenv("COLLECTION_NAME", "products")

    if cert:
        mongo = MongoClient(uri, tls=True, tlsCertificateKeyFile=cert)
    else:
        mongo = MongoClient(uri)

    voyage = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
    coll = mongo[db_name][coll_name]

    pending = coll.count_documents({"embedding": {"$exists": False}})
    total_docs = coll.count_documents({})
    print(f"Collection: {total_docs:,} total, {pending:,} need embeddings")

    if pending == 0:
        print("Nothing to do — all documents already have embeddings.")
        return

    if dry_run:
        print(f"DRY RUN: would embed {pending:,} documents in batches of {BATCH_SIZE}")
        return

    cursor = coll.find(
        {"embedding": {"$exists": False}},
        {"_id": 1, "title": 1, "description": 1, "features": 1},
        no_cursor_timeout=True,
    ).batch_size(BATCH_SIZE)

    total_updated = 0
    batch_docs: list[dict] = []

    try:
        for doc in cursor:
            batch_docs.append(doc)
            if len(batch_docs) < BATCH_SIZE:
                continue

            texts = [build_embed_text(d) for d in batch_docs]
            vectors = embed_batch(voyage, texts)

            ops = [
                UpdateOne({"_id": d["_id"]}, {"$set": {"embedding": v}})
                for d, v in zip(batch_docs, vectors)
            ]
            result = coll.bulk_write(ops, ordered=False)
            total_updated += result.modified_count
            print(f"  Embedded {total_updated:,} / {pending:,} documents...")
            batch_docs = []

        if batch_docs:
            texts = [build_embed_text(d) for d in batch_docs]
            vectors = embed_batch(voyage, texts)
            ops = [
                UpdateOne({"_id": d["_id"]}, {"$set": {"embedding": v}})
                for d, v in zip(batch_docs, vectors)
            ]
            result = coll.bulk_write(ops, ordered=False)
            total_updated += result.modified_count

    finally:
        cursor.close()

    print(f"\n✓ Done. {total_updated:,} products now have embeddings.")
    print("You can now run the demo: streamlit run app.py")


if __name__ == "__main__":
    main()
