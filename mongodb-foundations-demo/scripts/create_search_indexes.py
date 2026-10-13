#!/usr/bin/env python3
"""Create the two Atlas Search indexes the Search & RAG sections need.

    python3 scripts/create_search_indexes.py

Idempotent: creates the BM25 full-text index and the autoEmbed vector index on
`knowledge_chunks` if they do not already exist. Index builds are asynchronous —
Atlas reports the indexes as building for a minute or two, embedding every chunk
as it goes. Re-run `python3 scripts/search_status.py` to watch them turn READY.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo.errors import PyMongoError  # noqa: E402

from lib.mongo_client import DB_NAME, MissingUriError  # noqa: E402
from lib.search_config import KNOWLEDGE, is_seeded  # noqa: E402
from lib.search_index import (create_search_indexes,  # noqa: E402
                              search_index_status)


def main() -> int:
    print("Target: {}.{}".format(DB_NAME, KNOWLEDGE))
    try:
        if not is_seeded():
            print("ERROR: corpus is empty. Run: python3 seed_search.py")
            return 1
        created = create_search_indexes()
    except MissingUriError as exc:
        print("ERROR: {}".format(exc))
        return 1
    except PyMongoError as exc:
        print("ERROR: index creation failed — {}".format(exc))
        return 1

    if created:
        print("  ✓ requested: {}".format(", ".join(created)))
    else:
        print("  • both indexes already exist")

    for row in search_index_status():
        print("  {} {:<28} {}".format(
            "✓" if row["queryable"] else "…", row["index"], row["status"]))
    print("\nAtlas builds indexes asynchronously. Re-run "
          "`python3 scripts/search_status.py` until both are READY.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
