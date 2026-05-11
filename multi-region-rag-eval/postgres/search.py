"""Vector similarity search in pgvector with optional metadata pre-filtering."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import psycopg
from pgvector.psycopg import register_vector

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import load_settings  # noqa: E402
from embeddings import embed_account  # noqa: E402


def search(
    query_account: str,
    product_group: str,
    region: str | None,
    k: int = 5,
) -> tuple[list[dict[str, Any]], float]:
    settings = load_settings()
    query_vec = embed_account(query_account, product_group, settings.embed_dim)

    # Pre-filtering by region happens in the WHERE clause; the planner can use
    # the btree index on region to shrink the candidate set before the HNSW
    # probe runs. This is the optimisation the user asked us to demonstrate.
    sql = f"""
        SELECT account_name, product_group, region, sales_area,
               service_agent_id, operational_identity, regional_attrs,
               1 - (embedding <=> %s::vector) AS similarity
        FROM   {settings.pg_table}
        {{where}}
        ORDER  BY embedding <=> %s::vector
        LIMIT  %s
    """
    if region:
        sql = sql.format(where="WHERE region = %s")
        params: tuple = (query_vec, region, query_vec, k)
    else:
        sql = sql.format(where="")
        params = (query_vec, query_vec, k)

    with psycopg.connect(settings.pg_conn_str) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            start = time.perf_counter()
            cur.execute(sql, params)
            results = cur.fetchall()
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            colnames = [d.name for d in cur.description]
    return [dict(zip(colnames, row)) for row in results], elapsed_ms


def _format(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(no matches)"
    lines = []
    for r in rows:
        lines.append(
            f"  {r['similarity']:.4f}  {r['account_name']:<32} "
            f"region={r['region']:<8} agent={r['service_agent_id']} "
            f"area={r['sales_area']}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True,
                        help="Incoming (possibly misspelled) account name.")
    parser.add_argument("--product", default="Software")
    parser.add_argument("--region", default=None,
                        help="Optional pre-filter region (e.g. France).")
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()

    rows, elapsed = search(args.query, args.product, args.region, args.k)
    print(f"pgvector results in {elapsed:.1f} ms "
          f"(region pre-filter: {args.region or 'none'})")
    print(_format(rows))


if __name__ == "__main__":
    main()
