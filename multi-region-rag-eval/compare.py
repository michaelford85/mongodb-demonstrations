"""Run the same fuzzy lookup against both stores and print a side-by-side view.

Example incoming email subject lines (with deliberate typos) can be passed via
``--query``. Database connections are opened once and a throwaway warm-up
query is issued against each backend before the timed query runs, so the
reported latency reflects server-side work rather than one-shot client
bootstrap (SRV DNS, TLS, replica-set discovery, TCP/auth handshake).
"""
from __future__ import annotations

import argparse

import psycopg
from pgvector.psycopg import register_vector
from pymongo import MongoClient
from tabulate import tabulate

from config import load_settings
from mongodb.search import search as mongo_search
from postgres.search import search as pg_search


def _rows_for_table(rows: list[dict], backend: str) -> list[list]:
    # pgvector returns raw cosine similarity (1 - cosine_distance). Atlas
    # $vectorSearch with similarity:"cosine" returns (1 + cosine)/2, so we
    # unmap it back to raw cosine for a like-for-like display.
    out = []
    for r in rows:
        score = r["similarity"]
        if backend == "atlas":
            score = 2.0 * score - 1.0
        out.append([
            backend,
            f"{score:.4f}",
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

    settings = load_settings()

    # Open both connections once. Both clients are otherwise lazy/cold on
    # first wire op; hoisting them out of the per-call path is what makes
    # the side-by-side latency numbers comparable.
    with psycopg.connect(settings.pg_conn_str) as pg_conn, \
            MongoClient(settings.mongo_uri) as mongo_client:
        register_vector(pg_conn)
        mongo_coll = mongo_client[settings.mongo_db][settings.mongo_collection]

        # Untimed warm-up: a distinct, throwaway query that exercises the
        # full network/auth/index path so the timed query below measures
        # only the server-side ANN work and the protocol round-trip.
        pg_search("__warmup__", args.product, args.region, args.k, conn=pg_conn)
        mongo_search("__warmup__", args.product, args.region, args.k, coll=mongo_coll)

        pg_rows, pg_ms = pg_search(
            args.query, args.product, args.region, args.k, conn=pg_conn,
        )
        mongo_rows, mongo_ms = mongo_search(
            args.query, args.product, args.region, args.k, coll=mongo_coll,
        )

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
