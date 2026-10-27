#!/usr/bin/env python3
"""Create the Atlas Vector Search index (plus ordinary indexes) on the demo
read model, and wait until the index is READY.

Reads VOYAGE_DIMENSIONS / VOYAGE_MODEL from .env and uses them in the index
definition, so stored embeddings and the index always agree.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import atlas_collection, load_config  # noqa: E402


def wait_for_ready(index_name: str, collection, timeout_s: int = 600) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for idx in collection.list_search_indexes():
            if idx.get("name") == index_name and idx.get("status") == "READY":
                print(f"Index '{index_name}' is READY.")
                return
        print(f"Waiting for index '{index_name}' to become READY ...")
        time.sleep(10)
    raise SystemExit(f"Timed out waiting for index '{index_name}'.")


def main() -> None:
    cfg = load_config()
    collection = atlas_collection(cfg)

    vector_index = {
        "name": "search_items_vector",
        "type": "vectorSearch",
        "definition": {
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": cfg["voyage_dimensions"],
                    "similarity": "cosine",
                    "quantization": "none",
                },
                {
                    "type": "filter",
                    "path": "entity_type",
                },
                {
                    "type": "filter",
                    "path": "is_active",
                },
            ]
        },
    }

    print(
        f"Creating/ensuring vector index '{vector_index['name']}' "
        f"(numDimensions={cfg['voyage_dimensions']}, model={cfg['voyage_model']}) ..."
    )
    collection.create_search_index(vector_index)

    # Ordinary indexes for the read model.
    collection.create_index("source_id")
    collection.create_index("entity_type")
    collection.create_index("source_updated_at")

    wait_for_ready(vector_index["name"], collection)


if __name__ == "__main__":
    main()
