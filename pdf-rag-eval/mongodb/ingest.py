"""Bulk-load chunk documents into the MongoDB Atlas collection.

Writes the same chunk shape as cosmos/ingest.py, with the chunk_id used
as the document's _id so cross-store lookups are trivial.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pymongo import MongoClient, WriteConcern

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import CHUNKS_FILE, load_settings  # noqa: E402

BATCH_SIZE = 500


def _read_chunks(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _to_mongo_document(chunk: dict) -> dict:
    return {
        "_id": chunk["chunk_id"],
        "document_id": chunk["document_id"],
        "blob_path": chunk["blob_path"],
        "blob_url": chunk["blob_url"],
        "filename": chunk["filename"],
        "title": chunk["title"],
        "author": chunk["author"],
        "department": chunk["department"],
        "revision": chunk["revision"],
        "page_number": chunk["page_number"],
        "chunk_index": chunk["chunk_index"],
        "text": chunk["text"],
        "embedding": chunk["embedding"],
    }


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=CHUNKS_FILE)
    parser.add_argument(
        "--drop", action="store_true",
        help="Drop the collection before loading.",
    )
    args = parser.parse_args()

    if not args.chunks.exists():
        raise SystemExit(
            f"No chunks at {args.chunks}. Run embed_and_load.py first."
        )

    client = MongoClient(settings.mongo_uri)
    coll = client[settings.mongo_db].get_collection(
        settings.mongo_collection,
        write_concern=WriteConcern(w="majority"),
    )
    if args.drop:
        coll.drop()

    batch: list[dict] = []
    total = 0
    for chunk in _read_chunks(args.chunks):
        batch.append(_to_mongo_document(chunk))
        if len(batch) >= BATCH_SIZE:
            coll.insert_many(batch, ordered=False)
            total += len(batch)
            batch.clear()
    if batch:
        coll.insert_many(batch, ordered=False)
        total += len(batch)

    # Btree indexes for the filter fields used in the comparison demos.
    coll.create_index("document_id")
    coll.create_index("department")

    print(
        f"Inserted {total} chunks into "
        f"{settings.mongo_db}.{settings.mongo_collection}."
    )
    print(
        "Reminder: ensure the Atlas Vector Search index "
        f"'{settings.atlas_vector_index}' is created using "
        "mongodb/atlas_index.json before running searches "
        "(see mongodb/create_index.py)."
    )


if __name__ == "__main__":
    main()
