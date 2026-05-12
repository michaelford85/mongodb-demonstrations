"""Bulk-load chunk documents into the Cosmos DB container.

Reads chunks from data/chunks.jsonl (produced by embed_and_load.py) and
upserts each one through the SDK. The container partition key is
/document_id, so the SDK routes upserts to the right physical partition
without us having to specify it explicitly when the document carries the
field.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import CHUNKS_FILE, load_settings  # noqa: E402
from cosmos.client import ensure_container  # noqa: E402


def _read_chunks(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _to_cosmos_item(chunk: dict) -> dict:
    # Cosmos expects an `id` field; we mirror the chunk_id used by Mongo
    # so the same string identifies the same chunk in both stores.
    return {
        "id": chunk["chunk_id"],
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
    args = parser.parse_args()

    if not args.chunks.exists():
        raise SystemExit(
            f"No chunks at {args.chunks}. Run embed_and_load.py first."
        )

    container = ensure_container(settings)

    total = 0
    for chunk in _read_chunks(args.chunks):
        container.upsert_item(_to_cosmos_item(chunk))
        total += 1
        if total % 50 == 0:
            print(f"  upserted {total} chunks...")

    print(
        f"Upserted {total} chunks into Cosmos "
        f"{settings.cosmos_database}.{settings.cosmos_container}."
    )


if __name__ == "__main__":
    main()
