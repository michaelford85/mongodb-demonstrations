"""Seed the chunked-documents corpus for the Search & RAG sections.

    python3 seed_search.py

Deterministic and idempotent: it drops and rebuilds only the single
`knowledge_chunks` collection in `mongodb_foundations_demo` from the invented,
industry-neutral source articles in `lib/search_data.py`. No other collection
or database is read or modified.

The two Atlas Search indexes are created separately — run
`python3 scripts/create_search_indexes.py` after this. Automated Embedding then
embeds every chunk as Atlas builds the vector index.
"""

from __future__ import annotations

import sys

from pymongo.errors import PyMongoError

from lib.mongo_client import DB_NAME, MissingUriError
from lib.search_config import KNOWLEDGE
from lib.search_data import source_summary
from lib.search_seed import seed_knowledge


def main() -> int:
    print("Target database: {} · collection: {}".format(DB_NAME, KNOWLEDGE))
    try:
        result = seed_knowledge()
    except MissingUriError as exc:
        print("ERROR: {}".format(exc))
        return 1
    except PyMongoError as exc:
        print("ERROR: seed failed — {}".format(exc))
        return 1

    for row in source_summary():
        print("  ✓ {:<28} {} chunk(s)".format(row["title"], row["chunks"]))
    print("\n  {} chunks from {} documents seeded into `{}`."
          .format(result["chunks"], result["documents"], KNOWLEDGE))
    print("\nNext: python3 scripts/create_search_indexes.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
