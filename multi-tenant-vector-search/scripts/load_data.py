"""Generate and load the synthetic multi-tenant corpus, with embeddings.

Documents for every tenant (small and large) go into ONE base collection with a
`tenant_id` field. Embeddings are generated client-side so the same vectors are
visible to the shared flat index and to every large-tenant view.

    python scripts/load_data.py                      # PROFILE from .env, real embeddings
    python scripts/load_data.py --profile scale --fake-embeddings
    python scripts/load_data.py --drop               # wipe and reload from scratch

Safe to re-run: without --drop it refuses to load on top of existing data.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import InsertOne  # noqa: E402

from lib import tenants  # noqa: E402
from lib.client import (  # noqa: E402
    get_collection, DB_NAME, COLLECTION_NAME, PROFILE, BATCH_SIZE,
    TEXT_FIELD, EMBEDDING_FIELD,
)
from lib.embeddings import embed_texts  # noqa: E402


def _flush(coll, batch, fake):
    texts = [d[TEXT_FIELD] for d in batch]
    vectors = embed_texts(texts, input_type="document", fake=fake)
    ops = []
    for doc, vec in zip(batch, vectors):
        doc[EMBEDDING_FIELD] = vec
        ops.append(InsertOne(doc))
    coll.bulk_write(ops, ordered=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the multi-tenant corpus.")
    parser.add_argument("--profile", default=PROFILE, choices=list(tenants.PROFILES),
                        help=f"dataset profile (default from .env: {PROFILE})")
    parser.add_argument("--drop", action="store_true",
                        help="drop the collection before loading")
    parser.add_argument("--fake-embeddings", action="store_true",
                        help="use deterministic offline vectors (no Voyage key/cost)")
    args = parser.parse_args()

    coll = get_collection()

    if args.drop:
        coll.drop()
        print(f"Dropped {DB_NAME}.{COLLECTION_NAME}")

    if coll.estimated_document_count() and not args.drop:
        print(f"{DB_NAME}.{COLLECTION_NAME} already has documents. "
              f"Use --drop to reload from scratch.")
        return

    total = tenants.total_documents(args.profile)
    small = len(tenants.small_tenant_ids(args.profile))
    large = tenants.large_tenant_ids(args.profile)
    mode = "fake" if args.fake_embeddings else "Voyage AI"
    print(f"Profile '{args.profile}': {total:,} documents across "
          f"{small} small tenants + {len(large)} large tenants {large}")
    print(f"Embedding backend: {mode}. Loading in batches of {BATCH_SIZE}...")

    batch, inserted = [], 0
    for doc in tenants.generate_documents(args.profile):
        batch.append(doc)
        if len(batch) >= BATCH_SIZE:
            _flush(coll, batch, args.fake_embeddings)
            inserted += len(batch)
            batch = []
            print(f"  inserted {inserted:,} / {total:,}")
    if batch:
        _flush(coll, batch, args.fake_embeddings)
        inserted += len(batch)

    print(f"\nDone. Inserted {inserted:,} documents into {DB_NAME}.{COLLECTION_NAME}.")
    print("Next: python scripts/create_indexes.py --profile " + args.profile)


if __name__ == "__main__":
    main()
