"""Create (or inspect) the two Atlas search indexes this lab needs.

    python app/indexes.py            # create anything missing
    python app/indexes.py --status   # just report what exists and its state
    python app/indexes.py --drop     # remove both, e.g. to change EMBEDDING_DIM

Atlas builds search indexes asynchronously; --status is how you tell when they
are queryable. Requires an M10 or larger tier.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: E402
from pymongo.errors import OperationFailure  # noqa: E402
from pymongo.operations import SearchIndexModel  # noqa: E402


def _existing(coll) -> dict:
    try:
        return {ix["name"]: ix for ix in coll.list_search_indexes()}
    except OperationFailure as exc:
        raise RuntimeError(
            "Could not list search indexes. Atlas Search requires an M10 or "
            f"larger tier: {exc}"
        ) from exc


def text_index_model() -> SearchIndexModel:
    """BM25 over title and body — the keyword baseline."""
    return SearchIndexModel(
        name=config.TEXT_INDEX,
        type="search",
        definition={
            "mappings": {
                "dynamic": False,
                "fields": {
                    config.TITLE_FIELD: {"type": "string"},
                    config.BODY_FIELD: {"type": "string"},
                },
            }
        },
    )


def vector_index_model() -> SearchIndexModel:
    """HNSW over the client-side embeddings, with filterable metadata."""
    return SearchIndexModel(
        name=config.VECTOR_INDEX,
        type="vectorSearch",
        definition={
            "fields": [
                {
                    "type": "vector",
                    "path": config.EMBEDDING_FIELD,
                    "numDimensions": config.EMBEDDING_DIM,
                    "similarity": "cosine",
                },
                {"type": "filter", "path": "category"},
                {"type": "filter", "path": "product"},
            ]
        },
    )


def create() -> None:
    coll = config.get_articles()
    existing = _existing(coll)
    for model in (text_index_model(), vector_index_model()):
        name = model.document["name"]
        if name in existing:
            print(f"  '{name}' already exists — skipping.")
            continue
        coll.create_search_index(model)
        print(f"  created '{name}'.")
    print("\nAtlas builds these asynchronously. Poll with:")
    print("  python app/indexes.py --status")


def status() -> None:
    coll = config.get_articles()
    existing = _existing(coll)
    if not existing:
        print(f"No search indexes on {config.namespace()}.")
        return
    print(f"Search indexes on {config.namespace()}:")
    for name, ix in sorted(existing.items()):
        queryable = "queryable" if ix.get("queryable") else "not queryable yet"
        print(f"  {name:20s} type={ix.get('type', '?'):13s} "
              f"status={ix.get('status', '?'):10s} {queryable}")


def drop() -> None:
    coll = config.get_articles()
    existing = _existing(coll)
    for name in (config.TEXT_INDEX, config.VECTOR_INDEX):
        if name not in existing:
            print(f"  '{name}' does not exist — skipping.")
            continue
        coll.drop_search_index(name)
        print(f"  dropped '{name}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the lab's search indexes.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--status", action="store_true",
                       help="report index state and exit")
    group.add_argument("--drop", action="store_true",
                       help="drop both indexes")
    args = parser.parse_args()

    if args.status:
        status()
    elif args.drop:
        drop()
    else:
        print(f"Namespace: {config.namespace()}  "
              f"(dims={config.EMBEDDING_DIM}, similarity=cosine)")
        create()


if __name__ == "__main__":
    main()
