"""Load the synthetic dataset into Amazon RDS Postgres with pgvector."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import load_settings  # noqa: E402

SCHEMA_FILE = Path(__file__).parent / "schema.sql"
DATA_FILE = ROOT / "data" / "accounts.jsonl"


def _read_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _apply_schema(conn: psycopg.Connection, table: str, dim: int) -> None:
    ddl = SCHEMA_FILE.read_text(encoding="utf-8").format(table=table, dim=dim)
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def _truncate(conn: psycopg.Connection, table: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY")
    conn.commit()


def _copy_rows(conn: psycopg.Connection, table: str, rows: list[dict]) -> None:
    columns = (
        "account_name",
        "product_group",
        "case_reason",
        "operational_identity",
        "sales_area",
        "service_agent_id",
        "region",
        "regional_attrs",
        "embedding",
    )
    placeholders = ",".join(["%s"] * len(columns))
    sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
    batch: list[tuple] = []
    with conn.cursor() as cur:
        for row in rows:
            batch.append(
                (
                    row["account_name"],
                    row["product_group"],
                    row["case_reason"],
                    row["operational_identity"],
                    row["sales_area"],
                    row["service_agent_id"],
                    row["region"],
                    json.dumps(row["regional_attrs"]),
                    row["embedding"],
                )
            )
            if len(batch) >= 500:
                cur.executemany(sql, batch)
                batch.clear()
        if batch:
            cur.executemany(sql, batch)
    conn.commit()


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA_FILE)
    parser.add_argument("--truncate", action="store_true",
                        help="Truncate the table before loading.")
    args = parser.parse_args()

    rows = _read_rows(args.data)
    if not rows:
        raise SystemExit(f"No rows found in {args.data}; run generate_data.py first.")

    with psycopg.connect(settings.pg_conn_str) as conn:
        register_vector(conn)
        _apply_schema(conn, settings.pg_table, settings.embed_dim)
        if args.truncate:
            _truncate(conn, settings.pg_table)
        _copy_rows(conn, settings.pg_table, rows)
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {settings.pg_table}")
            total = cur.fetchone()[0]
    print(f"Loaded {len(rows)} rows; table now holds {total} rows.")


if __name__ == "__main__":
    main()
