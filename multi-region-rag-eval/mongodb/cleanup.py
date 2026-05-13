"""Delete the routing demo data from MongoDB Atlas.

Default behaviour is `collection.delete_many({})`, which removes every
document but keeps the collection, its btree indexes, and (importantly)
its Atlas Vector Search index intact.

Use `--drop` to remove the collection entirely. Note that dropping a
collection also removes any Atlas Vector Search indexes attached to it,
so the next ingest run will require re-creating the index from
`mongodb/atlas_index.json`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pymongo import MongoClient
from pymongo.uri_parser import parse_uri

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import load_settings  # noqa: E402


def cleanup(drop_collection: bool = False, assume_yes: bool = False) -> int:
    """Wipe the collection; return the document count remaining."""
    settings = load_settings()
    target = f"{settings.mongo_db}.{settings.mongo_collection}"
    op_label = "drop_collection" if drop_collection else "delete_many({})"

    if not assume_yes:
        prompt = (
            f"About to run {op_label} on {target} at "
            f"{_describe(settings.mongo_uri)}.\n"
            f"Type 'yes' to continue: "
        )
        if input(prompt).strip().lower() != "yes":
            print("Aborted.")
            return -1

    client = MongoClient(settings.mongo_uri)
    coll = client[settings.mongo_db][settings.mongo_collection]

    if drop_collection:
        coll.drop()
        print(
            f"Dropped collection {target}. Any Atlas Vector Search indexes "
            f"attached to it were removed with it; recreate them from "
            f"mongodb/atlas_index.json before the next search."
        )
        return 0

    result = coll.delete_many({})
    remaining = coll.estimated_document_count()
    print(
        f"Deleted {result.deleted_count} documents from {target}; "
        f"documents remaining: {remaining}."
    )
    return remaining


def _describe(uri: str) -> str:
    """Return a host-only summary suitable for the confirmation prompt."""
    try:
        parsed = parse_uri(uri)
        hosts = ",".join(f"{h}:{p}" for h, p in parsed["nodelist"])
        return hosts or "<unknown>"
    except Exception:
        return "<connection URI>"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--drop",
        action="store_true",
        help="drop_collection instead of delete_many({}).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    args = parser.parse_args()
    cleanup(drop_collection=args.drop, assume_yes=args.yes)


if __name__ == "__main__":
    main()
