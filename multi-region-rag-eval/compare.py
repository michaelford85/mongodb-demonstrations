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
from rerankers import rerank as voyage_rerank


def _atlas_cosine(score: float) -> float:
    # Atlas $vectorSearch with similarity:"cosine" returns (1+cosine)/2,
    # so we unmap it to raw cosine for parity with pgvector's 1-distance.
    return 2.0 * score - 1.0


def _rows_for_table(
    rows: list[dict], backend: str, *, with_rerank: bool,
) -> list[list]:
    out = []
    for r in rows:
        score = r["similarity"]
        if backend == "atlas":
            score = _atlas_cosine(score)
        row = [backend, f"{score:.4f}"]
        if with_rerank:
            rr = r.get("rerank_score")
            row.append(f"{rr:.4f}" if rr is not None else "")
        row.extend([
            r["account_name"],
            r["region"],
            r["product_group"],
            r["sales_area"],
            r["service_agent_id"],
        ])
        out.append(row)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True,
                        help="Misspelled or partial account_name from the inbound email.")
    parser.add_argument("--product", default="Software")
    parser.add_argument("--region", default=None,
                        help="Pre-filter region; omit for global search.")
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument(
        "--rerank", action="store_true",
        help="Apply Voyage AI rerank to each backend's candidate pool; the "
             "final table shows the reranker's top-k, not the vector top-k.",
    )
    parser.add_argument(
        "--rerank-candidates", type=int, default=25,
        help="When --rerank is set, fetch this many vector candidates per "
             "backend before reranking down to -k (default: 25).",
    )
    args = parser.parse_args()

    settings = load_settings()
    fetch_k = args.rerank_candidates if args.rerank else args.k

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
        pg_search("__warmup__", args.product, args.region, fetch_k, conn=pg_conn)
        mongo_search("__warmup__", args.product, args.region, fetch_k, coll=mongo_coll)

        pg_rows, pg_ms = pg_search(
            args.query, args.product, args.region, fetch_k, conn=pg_conn,
        )
        mongo_rows, mongo_ms = mongo_search(
            args.query, args.product, args.region, fetch_k, coll=mongo_coll,
        )

    pg_rerank_ms = mongo_rerank_ms = 0.0
    if args.rerank:
        pg_rows, pg_rerank_ms = voyage_rerank(
            args.query, pg_rows,
            api_key=settings.voyage_api_key,
            model=settings.voyage_rerank_model,
            top_k=args.k,
        )
        mongo_rows, mongo_rerank_ms = voyage_rerank(
            args.query, mongo_rows,
            api_key=settings.voyage_api_key,
            model=settings.voyage_rerank_model,
            top_k=args.k,
        )
    else:
        pg_rows = pg_rows[: args.k]
        mongo_rows = mongo_rows[: args.k]

    print(f"\nIncoming query: {args.query!r}  product={args.product}  "
          f"region={args.region or 'ALL'}  k={args.k}"
          + (f"  rerank=on (candidates={args.rerank_candidates}, "
             f"model={settings.voyage_rerank_model})" if args.rerank else ""))
    print(f"pgvector latency: {pg_ms:7.1f} ms  |  "
          f"Atlas Vector Search latency: {mongo_ms:7.1f} ms")
    if args.rerank:
        print(f"rerank latency:   {pg_rerank_ms:7.1f} ms  |  "
              f"                            {mongo_rerank_ms:7.1f} ms")
    print()

    headers = ["backend", "score"]
    if args.rerank:
        headers.append("rerank")
    headers += ["account_name", "region", "product_group", "sales_area", "agent_id"]
    table = (
        _rows_for_table(pg_rows, "pgvector", with_rerank=args.rerank)
        + _rows_for_table(mongo_rows, "atlas", with_rerank=args.rerank)
    )
    print(tabulate(table, headers=headers, tablefmt="github"))


if __name__ == "__main__":
    main()
