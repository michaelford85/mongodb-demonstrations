"""Delete the routing demo data from Postgres.

Default behaviour is `TRUNCATE TABLE ... RESTART IDENTITY`, which removes
every row but keeps the table definition, its indexes, and the pgvector
extension intact — the fastest way to reset between ingest runs.

Use `--drop-table` to also remove the table itself (the next ingest will
recreate it from `postgres/schema.sql`). The `vector` extension is left
installed in both cases.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import load_settings  # noqa: E402


def cleanup(drop_table: bool = False, assume_yes: bool = False) -> int:
    """Wipe the table; return the row count remaining after the operation."""
    settings = load_settings()
    target = f"{settings.pg_table}"
    op_label = "DROP TABLE" if drop_table else "TRUNCATE TABLE"

    if not assume_yes:
        prompt = (
            f"About to {op_label} {target} on {_describe(settings.pg_conn_str)}.\n"
            f"Type 'yes' to continue: "
        )
        if input(prompt).strip().lower() != "yes":
            print("Aborted.")
            return -1

    with psycopg.connect(settings.pg_conn_str) as conn:
        with conn.cursor() as cur:
            if drop_table:
                cur.execute(f"DROP TABLE IF EXISTS {settings.pg_table}")
            else:
                # TRUNCATE on a missing table errors, so guard it.
                cur.execute(
                    "SELECT to_regclass(%s) IS NOT NULL",
                    (settings.pg_table,),
                )
                exists = cur.fetchone()[0]
                if exists:
                    cur.execute(
                        f"TRUNCATE TABLE {settings.pg_table} RESTART IDENTITY"
                    )
        conn.commit()

        remaining = 0
        if not drop_table:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE((SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_name = %s), 0)",
                    (settings.pg_table,),
                )
                if cur.fetchone()[0]:
                    cur.execute(f"SELECT COUNT(*) FROM {settings.pg_table}")
                    remaining = cur.fetchone()[0]

    if drop_table:
        print(f"Dropped table {settings.pg_table}.")
    else:
        print(f"Truncated {settings.pg_table}; rows remaining: {remaining}.")
    return remaining


def _describe(conn_str: str) -> str:
    """Return a host-only summary suitable for the confirmation prompt."""
    try:
        info = psycopg.conninfo.conninfo_to_dict(conn_str)
        host = info.get("host", "<unknown>")
        db = info.get("dbname", "<unknown>")
        return f"{host}/{db}"
    except Exception:
        return "<connection string>"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--drop-table",
        action="store_true",
        help="DROP TABLE instead of TRUNCATE. Indexes are removed with it.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    args = parser.parse_args()
    cleanup(drop_table=args.drop_table, assume_yes=args.yes)


if __name__ == "__main__":
    main()
