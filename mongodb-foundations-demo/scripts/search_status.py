#!/usr/bin/env python3
"""Report Search & RAG readiness from the command line.

    python3 scripts/search_status.py

Prints whether the chunked corpus is seeded, whether both Atlas Search indexes
are queryable, and whether the optional Voyage reranker and LLM generation are
configured. No secret is printed — the key checks report presence only.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo.errors import PyMongoError  # noqa: E402

from lib.mongo_client import DB_NAME, MissingUriError  # noqa: E402
from lib.search_config import (KNOWLEDGE, generation_available,  # noqa: E402
                               knowledge_count, rerank_available)
from lib.search_index import search_index_status  # noqa: E402


def main() -> int:
    print("MongoDB Search & RAG — readiness\n")
    print("Namespace: {}.{}\n".format(DB_NAME, KNOWLEDGE))
    ok = True
    try:
        count = knowledge_count()
        print("  {} corpus seeded            {} chunk(s)"
              .format("✓" if count else "✗", count))
        ok = ok and bool(count)
        for row in search_index_status():
            print("  {} index {:<22} {}".format(
                "✓" if row["queryable"] else "✗", row["index"], row["status"]))
            ok = ok and row["queryable"]
    except MissingUriError as exc:
        print("  ✗ {}".format(exc))
        return 1
    except PyMongoError as exc:
        print("  ✗ cannot reach deployment — {}".format(exc))
        return 1

    print("  {} rerank (optional)         VOYAGE_API_KEY {}"
          .format("✓" if rerank_available() else "•",
                  "set" if rerank_available() else "not set"))
    print("  {} generation (optional)     GEN_API_KEY {}"
          .format("✓" if generation_available() else "•",
                  "set" if generation_available() else "not set"))

    print()
    if ok:
        print("Search & RAG ready. Open sections ⑧ and ⑨ in the app.")
        return 0
    print("Not ready. Seed: python3 seed_search.py · "
          "Index: python3 scripts/create_search_indexes.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
