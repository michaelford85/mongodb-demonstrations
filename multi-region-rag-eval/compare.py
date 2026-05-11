"""Run the same fuzzy lookup against both stores and print a side-by-side view.

Example incoming email subject lines (with deliberate typos) can be passed via
``--query``. The script generates the query embedding once and reuses it for
each backend so the comparison is apples-to-apples.
"""
from __future__ import annotations

import argparse

from tabulate import tabulate

from mongodb.search import search as mongo_search
from postgres.search import search as pg_search


def _rows_for_table(rows: list[dict], backend: str) -> list[list]:
    out = []
    for r in rows:
        out.append([
            backend,
            f"{r['similarity']:.4f}",
            r["account_name"],
            r["region"],
            r["product_group"],
            r["sales_area"],
            r["service_agent_id"],
        ])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True,
                        help="Misspelled or partial account_name from the inbound email.")
    parser.add_argument("--product", default="Software")
    parser.add_argument("--region", default=None,
                        help="Pre-filter region; omit for global search.")
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()

    pg_rows, pg_ms = pg_search(args.query, args.product, args.region, args.k)
    mongo_rows, mongo_ms = mongo_search(args.query, args.product, args.region, args.k)

    print(f"\nIncoming query: {args.query!r}  product={args.product}  "
          f"region={args.region or 'ALL'}  k={args.k}")
    print(f"pgvector latency: {pg_ms:7.1f} ms  |  "
          f"Atlas Vector Search latency: {mongo_ms:7.1f} ms\n")

    headers = ["backend", "score", "account_name", "region",
               "product_group", "sales_area", "agent_id"]
    table = _rows_for_table(pg_rows, "pgvector") + _rows_for_table(mongo_rows, "atlas")
    print(tabulate(table, headers=headers, tablefmt="github"))


if __name__ == "__main__":
    main()
