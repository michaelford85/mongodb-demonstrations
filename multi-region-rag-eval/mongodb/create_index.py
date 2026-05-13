"""Create or update the Atlas Search indexes for the demo collection.

Provisions both index definitions in ``mongodb/`` by default:

* ``atlas_index.json`` — the vectorSearch index used by mongodb/search.py
  and compare.py.
* ``atlas_search_index.json`` — the Lucene BM25 index used by
  mongodb/hybrid_search.py to add a lexical-similarity arm alongside the
  vector arm.

Reads each JSON, substitutes ``${VOYAGE_MODEL}`` with the embedding model
configured in .env (a no-op for the BM25 index), and applies the result
via PyMongo's ``create_search_index`` / ``update_search_index`` APIs
(Atlas only).

This is the one Atlas-side artifact that the provisioning Terraform projects
in this repository cannot stand up for you, so it lives here as a one-shot
helper rather than as a step inside ingest.py.
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

INDEX_DIR = Path(__file__).resolve().parent
DEFAULT_INDEX_FILES = (
    INDEX_DIR / "atlas_index.json",
    INDEX_DIR / "atlas_search_index.json",
)


def _load_index_spec(path: Path, voyage_model: str) -> dict:
    raw = path.read_text(encoding="utf-8")
    # Single placeholder substitution keeps the JSON file valid on disk and
    # avoids pulling in a templating dependency.
    resolved = raw.replace("${VOYAGE_MODEL}", voyage_model)
    return json.loads(resolved)


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
        f"Timed out after {timeout_s:.0f}s waiting for index '{name}' to "
        "become queryable. Atlas continues building it in the background; "
        "re-run with --wait to keep polling."
    )


def _apply_one(coll, path: Path, voyage_model: str, replace: bool) -> str:
    spec = _load_index_spec(path, voyage_model)
    name = spec["name"]
    definition = spec["definition"]
    index_type = spec.get("type", "vectorSearch")

    existing = _existing_index(coll, name)
    if existing and replace:
        print(f"Dropping existing index '{name}' (--replace).")
        coll.drop_search_index(name)
        # Atlas needs a moment between drop and create.
        while _existing_index(coll, name) is not None:
            time.sleep(2.0)
        existing = None

    if existing is None:
        print(
            f"Creating Atlas Search index '{name}' (type={index_type}) on "
            f"{coll.database.name}.{coll.name} from {path.name}..."
        )
        coll.create_search_index(
            model=SearchIndexModel(
                name=name,
                definition=definition,
                type=index_type,
            )
        )
    else:
        print(
            f"Updating existing index '{name}' (type={index_type}) on "
            f"{coll.database.name}.{coll.name} from {path.name}..."
        )
        coll.update_search_index(name=name, definition=definition)
    return name


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--definition", type=Path, action="append", default=None,
        help="Index definition JSON to provision; may be passed multiple "
             "times. Default: provision both atlas_index.json and "
             "atlas_search_index.json.",
    )
    parser.add_argument(
        "--wait", action="store_true",
        help="Block until each provisioned index reports queryable=true.",
    )
    parser.add_argument(
        "--timeout", type=float, default=600.0,
        help="Seconds to wait per index when --wait is set (default: 600).",
    )
    parser.add_argument(
        "--replace", action="store_true",
        help="If a target index already exists, drop and recreate it.",
    )
    args = parser.parse_args()

    definitions = list(args.definition) if args.definition else list(DEFAULT_INDEX_FILES)

    client = MongoClient(settings.mongo_uri)
    coll = client[settings.mongo_db][settings.mongo_collection]

    submitted: list[str] = []
    for path in definitions:
        submitted.append(_apply_one(coll, path, settings.voyage_model, args.replace))

    if args.wait:
        for name in submitted:
            _wait_until_queryable(coll, name, args.timeout)
    else:
        print(
            "Submitted. Indexes build asynchronously on Atlas; "
            "pass --wait to block until each is queryable."
        )


if __name__ == "__main__":
    main()
