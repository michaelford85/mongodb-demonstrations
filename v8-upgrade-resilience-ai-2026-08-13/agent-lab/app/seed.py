"""Load the synthetic tickets into MongoDB.

    python app/seed.py                 # load, drop first if already present
    python app/seed.py --keep          # add without dropping
    python app/seed.py --embed         # also store embeddings (for vector search)
    python app/seed.py --vector-index  # create the Atlas vector index (M10+)
    python app/seed.py --status        # what is currently loaded

`age_hours` in the JSON is converted to a real `created_at` relative to *now*,
so tools like get_recent_tickets stay meaningful whenever the lab is run.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: E402
import embeddings  # noqa: E402
from pymongo import ASCENDING, DESCENDING  # noqa: E402
from pymongo.errors import OperationFailure  # noqa: E402
from pymongo.operations import SearchIndexModel  # noqa: E402


def _load_file() -> list:
    if not config.DATA_FILE.exists():
        raise SystemExit(
            f"{config.DATA_FILE} not found. Run: python data/build_tickets.py")
    return json.loads(config.DATA_FILE.read_text())


def _embed_input(doc: dict) -> str:
    return f"{doc['title']}\n{doc['description']}"


def seed(drop: bool, embed: bool) -> None:
    tickets = _load_file()
    coll = config.get_tickets()

    if drop:
        coll.drop()
        print(f"Dropped {config.namespace()}")

    now = datetime.now(timezone.utc)
    docs = []
    for t in tickets:
        doc = dict(t)
        age = doc.pop("age_hours")
        doc["created_at"] = now - timedelta(hours=age)
        # Resolved and closed tickets need a plausible end date after creation.
        if doc["status"] in ("resolved", "closed"):
            doc["resolved_at"] = doc["created_at"] + timedelta(
                hours=min(age * 0.5, 48))
        docs.append(doc)

    if embed:
        print(f"Embedding {len(docs)} tickets with "
              f"{config.EMBEDDING_PROVIDER} ({config.EMBEDDING_DIM} dims)...")
        batch_size = config.EMBEDDING_BATCH_SIZE
        for start in range(0, len(docs), batch_size):
            batch = docs[start:start + batch_size]
            vectors = embeddings.embed_texts([_embed_input(d) for d in batch])
            for doc, vec in zip(batch, vectors):
                doc[config.EMBEDDING_FIELD] = vec
            print(f"  embedded {min(start + batch_size, len(docs))} / {len(docs)}")

    coll.insert_many(docs)
    coll.create_index([("ticket_id", ASCENDING)], unique=True)
    coll.create_index([("created_at", DESCENDING)])
    coll.create_index([("status", ASCENDING), ("priority", ASCENDING)])

    print(f"\nInserted {len(docs)} tickets into {config.namespace()}.")
    print("Indexes: ticket_id (unique), created_at, status+priority")
    if embed:
        print("Next: python app/seed.py --vector-index, then set "
              "USE_VECTOR_SEARCH=true")
    else:
        print("Next: python app/main.py")


def create_vector_index() -> None:
    coll = config.get_tickets()
    try:
        existing = {ix["name"] for ix in coll.list_search_indexes()}
    except OperationFailure as exc:
        raise SystemExit(
            "Could not list search indexes. Atlas Vector Search requires an "
            f"M10 or larger tier: {exc}"
        ) from exc

    if config.VECTOR_INDEX in existing:
        print(f"'{config.VECTOR_INDEX}' already exists — skipping.")
    else:
        coll.create_search_index(SearchIndexModel(
            name=config.VECTOR_INDEX,
            type="vectorSearch",
            definition={"fields": [
                {"type": "vector", "path": config.EMBEDDING_FIELD,
                 "numDimensions": config.EMBEDDING_DIM, "similarity": "cosine"},
                {"type": "filter", "path": "status"},
                {"type": "filter", "path": "priority"},
            ]},
        ))
        print(f"Created '{config.VECTOR_INDEX}' "
              f"({config.EMBEDDING_DIM} dims, cosine).")
    print("Atlas builds this asynchronously; re-run --status until queryable.")


def status() -> None:
    coll = config.get_tickets()
    total = coll.count_documents({})
    print(f"{config.namespace()}: {total} tickets")
    if not total:
        print("Nothing loaded. Run: python app/seed.py")
        return
    with_vec = coll.count_documents({config.EMBEDDING_FIELD: {"$exists": True}})
    print(f"  with embeddings: {with_vec}")
    for row in coll.aggregate([
        {"$group": {"_id": "$status", "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}
    ]):
        print(f"  status {row['_id']:22s} {row['n']}")
    try:
        for ix in coll.list_search_indexes():
            print(f"  search index '{ix['name']}' status={ix.get('status')} "
                  f"queryable={ix.get('queryable')}")
    except OperationFailure:
        print("  search indexes: not available on this deployment")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the ticket dataset.")
    parser.add_argument("--keep", action="store_true",
                        help="do not drop the collection first")
    parser.add_argument("--embed", action="store_true",
                        help="store an embedding on each ticket")
    parser.add_argument("--vector-index", action="store_true",
                        help="create the Atlas vector index and exit")
    parser.add_argument("--status", action="store_true",
                        help="report what is loaded and exit")
    args = parser.parse_args()

    if args.status:
        status()
    elif args.vector_index:
        create_vector_index()
    else:
        seed(drop=not args.keep, embed=args.embed)


if __name__ == "__main__":
    main()
