"""Load the synthetic dataset into a MongoDB Atlas collection.

The document model is intentionally polymorphic: region-specific fields live at
the top level of the document rather than inside a sub-object, which is the
counterpart of the JSONB approach demonstrated for Postgres.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pymongo import MongoClient, WriteConcern

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import load_settings  # noqa: E402

DATA_FILE = ROOT / "data" / "accounts.jsonl"
BATCH_SIZE = 500


def _read_rows(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _to_document(row: dict) -> dict:
    """Flatten regional_attrs to the top level to showcase polymorphic BSON.

    We persist both the composed ``embedding_text`` (useful for diagnostics)
    and the precomputed ``embedding`` vector produced by generate_data.py.
    The Atlas Vector Search index is built over the ``embedding`` field so
    both backends compare against the *same* Voyage AI vectors.
    """
    doc = {
        "account_name": row["account_name"],
        "product_group": row["product_group"],
        "case_reason": row["case_reason"],
        "operational_identity": row["operational_identity"],
        "sales_area": row["sales_area"],
        "service_agent_id": row["service_agent_id"],
        "region": row["region"],
        "embedding_text": row["embedding_text"],
        "embedding": row["embedding"],
    }
    # Same collection, different shape per region. No migration needed.
    doc.update(row["regional_attrs"])
    return doc


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA_FILE)
    parser.add_argument("--drop", action="store_true",
                        help="Drop the collection before loading.")
    args = parser.parse_args()

    if not args.data.exists():
        raise SystemExit(f"No data at {args.data}; run generate_data.py first.")

    client = MongoClient(settings.mongo_uri)
    coll = client[settings.mongo_db].get_collection(
        settings.mongo_collection,
        write_concern=WriteConcern(w="majority"),
    )
    if args.drop:
        coll.drop()

    batch: list[dict] = []
    total = 0
    for row in _read_rows(args.data):
        batch.append(_to_document(row))
        if len(batch) >= BATCH_SIZE:
            coll.insert_many(batch, ordered=False)
            total += len(batch)
            batch.clear()
    if batch:
        coll.insert_many(batch, ordered=False)
        total += len(batch)

    # A standard btree index speeds up the region pre-filter even when the
    # Atlas vector index is not yet warm.
    coll.create_index("region")
    coll.create_index("product_group")

    print(
        f"Inserted {total} documents into "
        f"{settings.mongo_db}.{settings.mongo_collection}. "
        f"Total documents: {coll.estimated_document_count()}."
    )
    print(
        "Reminder: ensure the Atlas Vector Search index "
        f"'{settings.atlas_vector_index}' is created using "
        "mongodb/atlas_index.json before running searches "
        "(see mongodb/create_index.py)."
    )


if __name__ == "__main__":
    main()
