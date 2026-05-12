"""Create or update the Atlas Vector Search index for the demo collection.

Reads mongodb/atlas_index.json and applies it via PyMongo's
create_search_index / update_search_index APIs. Mirrors the helper used
by multi-region-rag-eval so behaviour is consistent across demos.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import load_settings  # noqa: E402

INDEX_FILE = Path(__file__).resolve().parent / "atlas_index.json"


def _existing_index(coll, name: str) -> dict | None:
    for idx in coll.list_search_indexes():
        if idx.get("name") == name:
            return idx
    return None


def _wait_until_queryable(coll, name: str, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        idx = _existing_index(coll, name)
        if idx and idx.get("queryable"):
            print(f"Index '{name}' is queryable.")
            return
        status = idx.get("status") if idx else "PENDING"
        print(f"  ...waiting (status={status})")
        time.sleep(5.0)
    print(
        f"Timed out after {timeout_s:.0f}s waiting for index '{name}'. "
        "Atlas continues building it in the background."
    )


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", type=Path, default=INDEX_FILE)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    spec = json.loads(args.definition.read_text(encoding="utf-8"))
    name = spec.get("name") or settings.atlas_vector_index
    definition = spec["definition"]

    client = MongoClient(settings.mongo_uri)
    coll = client[settings.mongo_db][settings.mongo_collection]

    existing = _existing_index(coll, name)
    if existing and args.replace:
        print(f"Dropping existing index '{name}' (--replace).")
        coll.drop_search_index(name)
        while _existing_index(coll, name) is not None:
            time.sleep(2.0)
        existing = None

    if existing is None:
        print(
            f"Creating Atlas Vector Search index '{name}' on "
            f"{settings.mongo_db}.{settings.mongo_collection}..."
        )
        coll.create_search_index(
            model=SearchIndexModel(
                name=name,
                definition=definition,
                type=spec.get("type", "vectorSearch"),
            )
        )
    else:
        print(
            f"Updating existing index '{name}' on "
            f"{settings.mongo_db}.{settings.mongo_collection}..."
        )
        coll.update_search_index(name=name, definition=definition)

    if args.wait:
        _wait_until_queryable(coll, name, args.timeout)
    else:
        print("Submitted. Pass --wait to block until queryable.")


if __name__ == "__main__":
    main()
