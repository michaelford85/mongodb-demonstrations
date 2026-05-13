"""Wipe the routing demo data from both clusters in one shot.

Defaults to TRUNCATE / delete_many({}) so the schema, indexes, and the
pgvector extension survive. Pass `--drop` to also remove the table and
the collection themselves.
"""
from __future__ import annotations

import argparse

from mongodb.cleanup import cleanup as mongo_cleanup
from postgres.cleanup import cleanup as pg_cleanup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--drop",
        action="store_true",
        help="DROP TABLE / drop_collection instead of truncating/deleting docs.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip both interactive confirmations.",
    )
    args = parser.parse_args()

    print("=== Postgres ===")
    pg_cleanup(drop_table=args.drop, assume_yes=args.yes)
    print()
    print("=== MongoDB Atlas ===")
    mongo_cleanup(drop_collection=args.drop, assume_yes=args.yes)


if __name__ == "__main__":
    main()
