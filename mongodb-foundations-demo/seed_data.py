"""Seed (or re-seed) the dedicated demo namespace.

    python3 seed_data.py

Idempotent and deterministic: it drops and rebuilds only the three collections
in `mongodb_foundations_demo` — applying each collection's `$jsonSchema`
validator first — then creates the five demo indexes.
No other database on the deployment is read or modified.
"""

from __future__ import annotations

import sys

from pymongo.errors import PyMongoError

from lib.mongo_client import DB_NAME, MissingUriError
from lib.schema import VALIDATORS
from lib.seed import REQUIRED_INDEXES, seed


def main() -> int:
    print("Target database: {}".format(DB_NAME))
    try:
        result = seed()
    except MissingUriError as exc:
        print("ERROR: {}".format(exc))
        return 1
    except PyMongoError as exc:
        print("ERROR: seed failed — {}".format(exc))
        return 1

    for name, count in result.items():
        print("  ✓ {:<13} {} documents".format(name, count))
    total = sum(len(specs) for specs in REQUIRED_INDEXES.values())
    print("  ✓ {} demo indexes created".format(total))
    print("  ✓ {} schema validators applied".format(len(VALIDATORS)))
    print("\nNext: streamlit run app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
