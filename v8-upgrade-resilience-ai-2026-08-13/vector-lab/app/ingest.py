"""Load the generated corpus into MongoDB, embedding each article on the way in.

    python app/ingest.py                  # load anything not already present
    python app/ingest.py --drop           # wipe the collection and reload
    python app/ingest.py --re-embed       # keep documents, recompute vectors

Re-runnable: without --drop, documents already carrying an embedding are left
alone, so an interrupted run can simply be repeated.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: E402
import embeddings  # noqa: E402
from pymongo import UpdateOne  # noqa: E402


def _load_file() -> list:
    if not config.DATA_FILE.exists():
        raise SystemExit(
            f"{config.DATA_FILE} not found. Run: python data/build_corpus.py"
        )
    return json.loads(config.DATA_FILE.read_text())


def _embed_input(doc: dict) -> str:
    """Title and body together — the title carries real signal in a KB."""
    return f"{doc[config.TITLE_FIELD]}\n{doc[config.BODY_FIELD]}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the DocsCo corpus.")
    parser.add_argument("--drop", action="store_true",
                        help="drop the collection before loading")
    parser.add_argument("--re-embed", action="store_true",
                        help="recompute embeddings for documents that have one")
    args = parser.parse_args()

    articles = _load_file()
    coll = config.get_articles()

    if args.drop:
        coll.drop()
        print(f"Dropped {config.namespace()}")

    coll.create_index("doc_id", unique=True)

    if args.re_embed:
        pending = articles
    else:
        have = {d["doc_id"] for d in
                coll.find({config.EMBEDDING_FIELD: {"$exists": True}},
                          {"doc_id": 1})}
        pending = [a for a in articles if a["doc_id"] not in have]

    print(f"Namespace: {config.namespace()}")
    print(f"Provider:  {config.EMBEDDING_PROVIDER} "
          f"(model={config.EMBEDDING_MODEL}, dims={config.EMBEDDING_DIM})")
    print(f"Articles:  {len(articles)} in file, {len(pending)} to embed")

    if not pending:
        print("Nothing to do. Use --re-embed to recompute, --drop to reload.")
        return

    batch_size = config.EMBEDDING_BATCH_SIZE
    done = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start:start + batch_size]
        vectors = embeddings.embed_texts(
            [_embed_input(d) for d in batch], input_type="document")
        if len(vectors) != len(batch):
            raise RuntimeError(
                f"Provider returned {len(vectors)} vectors for {len(batch)} texts")
        ops = []
        for doc, vec in zip(batch, vectors):
            if len(vec) != config.EMBEDDING_DIM:
                raise RuntimeError(
                    f"{doc['doc_id']}: got {len(vec)} dimensions, EMBEDDING_DIM "
                    f"is {config.EMBEDDING_DIM}. Fix .env, then re-create the "
                    f"vector index."
                )
            payload = dict(doc)
            payload[config.EMBEDDING_FIELD] = vec
            ops.append(UpdateOne({"doc_id": doc["doc_id"]},
                                 {"$set": payload}, upsert=True))
        coll.bulk_write(ops, ordered=False)
        done += len(batch)
        print(f"  embedded and wrote {done} / {len(pending)}")

    print(f"\nDone. {coll.count_documents({})} documents in {config.namespace()}.")
    print("Next: python app/indexes.py")


if __name__ == "__main__":
    main()
