"""Create the two Atlas Search indexes the lab relies on.

  1. A Vector Search index of type `autoEmbed` on the plot field. Atlas
     generates the embeddings itself (at index-time AND query-time) using
     the Voyage AI model in .env — so neither the GUI nor mongosh ever
     computes a vector. You query with plain natural-language text.

  2. An Atlas Search (BM25) index on the same plot field for keyword search.

Both are created with the same names the GUI and README use, so the mongosh
snippets in the README work verbatim.

    python scripts/create_indexes.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo.operations import SearchIndexModel  # noqa: E402

from lib.client import (  # noqa: E402
    get_collection, VECTOR_INDEX, TEXT_INDEX,
    EMBEDDING_MODEL, EMBEDDING_DIM, SEARCH_FIELD,
)


def _existing(coll) -> set:
    return {ix["name"] for ix in coll.list_search_indexes()}


def main() -> None:
    coll = get_collection()
    existing = _existing(coll)

    # ── 1. autoEmbed vector index ────────────────────────────────────────────
    if VECTOR_INDEX in existing:
        print(f"Vector index '{VECTOR_INDEX}' already exists — skipping.")
    else:
        coll.create_search_index(
            SearchIndexModel(
                name=VECTOR_INDEX,
                type="vectorSearch",
                definition={
                    "fields": [
                        {
                            "type": "autoEmbed",
                            "modality": "text",
                            "path": SEARCH_FIELD,
                            "model": EMBEDDING_MODEL,
                            "numDimensions": EMBEDDING_DIM,
                            "similarity": "cosine",
                        }
                    ]
                },
            )
        )
        print(f"Created autoEmbed vector index '{VECTOR_INDEX}' "
              f"on '{SEARCH_FIELD}' using model '{EMBEDDING_MODEL}'.")

    # ── 2. BM25 keyword index ────────────────────────────────────────────────
    if TEXT_INDEX in existing:
        print(f"Text index '{TEXT_INDEX}' already exists — skipping.")
    else:
        coll.create_search_index(
            SearchIndexModel(
                name=TEXT_INDEX,
                type="search",
                definition={
                    "mappings": {
                        "dynamic": False,
                        "fields": {
                            SEARCH_FIELD: {"type": "string"},
                            "title": {"type": "string"},
                        },
                    }
                },
            )
        )
        print(f"Created Atlas Search (BM25) index '{TEXT_INDEX}' "
              f"on '{SEARCH_FIELD}' and 'title'.")

    print("\nAtlas builds indexes asynchronously. Wait 1-2 minutes, then check")
    print("the Atlas UI -> Search Indexes, or run: python scripts/status.py")


if __name__ == "__main__":
    main()
