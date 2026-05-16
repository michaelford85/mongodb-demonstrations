"""Concurrent vector-search load against both backends.

Spins up N worker threads that hammer each store with the canned query
set for `duration_s` seconds. Records latency and any failures, then
prints a side-by-side table. The interesting datapoint on Cosmos is the
throttled column (HTTP 429 / "Request rate is too large") once
concurrency exceeds what the configured autoscale RU/s ceiling can
serve; Atlas tier connection headroom is much higher, so successes
typically dominate at the same concurrency.

On a small corpus at default --workers 16 / --top-k 5, the per-query RU
cost stays well under the 1000 RU/s autoscale floor and no throttling
appears. --ru-stress raises the defaults to --workers 64 --top-k 50,
which combines higher concurrency with a more expensive scan per query
and is the quickest way to force 429s on Cosmos for a demo.

By default the Cosmos SDK auto-retries 429s up to 9 times with 30s of
total backoff, so a saturated container shows up as inflated latency
rather than throttled requests. --surface-throttles disables that auto-
retry so 429s land in the 'throttled' column instead of being absorbed
as silent p99 inflation. Pair it with --ru-stress for the full demo.

Usage:
    python -m compare.connections --workers 16 --duration 30
    python -m compare.connections --ru-stress                       # workers=64, top_k=50
    python -m compare.connections --ru-stress --surface-throttles   # full throttle demo
    python -m compare.connections --ru-stress --workers 128         # override one knob
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from azure.cosmos import CosmosClient
from azure.cosmos import documents as cosmos_documents
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compare.common import (  # noqa: E402
    CANNED_QUERIES,
    Timing,
    embed_canned_queries,
    format_stats_table,
    summarise,
    time_call,
)
from config import Settings, load_settings  # noqa: E402


def _cosmos_search(container, vector: list[float], top_k: int) -> int:
    query = (
        "SELECT TOP @k c.id, "
        "VectorDistance(c.embedding, @vec) AS score "
        "FROM c ORDER BY VectorDistance(c.embedding, @vec)"
    )
    parameters = [
        {"name": "@k", "value": top_k},
        {"name": "@vec", "value": vector},
    ]
    items = list(
        container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True,
        )
    )
    return len(items)


def _atlas_search(coll, index_name: str, vector: list[float], top_k: int) -> int:
    pipeline = [
        {
            "$vectorSearch": {
                "index": index_name,
                "path": "embedding",
                "queryVector": vector,
                "numCandidates": max(top_k * 10, 50),
                "limit": top_k,
            }
        },
        {"$project": {"_id": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]
    return len(list(coll.aggregate(pipeline)))


def _run_load(
    label: str,
    workers: int,
    duration_s: float,
    do_one: Callable[[list[float]], object],
    vectors: list[list[float]],
) -> tuple[list[Timing], float]:
    deadline = time.perf_counter() + duration_s
    timings: list[Timing] = []
    rng = random.Random(label)

    def worker_loop() -> list[Timing]:
        local: list[Timing] = []
        while time.perf_counter() < deadline:
            vec = vectors[rng.randrange(len(vectors))]
            local.append(time_call(lambda v=vec: do_one(v)))
        return local

    print(f"[{label}] starting {workers} workers for {duration_s:.0f}s...")
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker_loop) for _ in range(workers)]
        for fut in as_completed(futures):
            timings.extend(fut.result())
    elapsed = time.perf_counter() - started
    print(f"[{label}] done. {len(timings)} requests in {elapsed:.1f}s.")
    return timings, elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=None,
                        help="Worker threads (default: 16, or 64 with --ru-stress).")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--top-k", type=int, default=None,
                        help="Top-k per query (default: 5, or 50 with --ru-stress).")
    parser.add_argument("--ru-stress", action="store_true",
                        help="Preset that bumps --workers to 64 and --top-k to 50 "
                             "so per-query RU cost x concurrency comfortably exceeds "
                             "the Cosmos autoscale ceiling. Explicit --workers / "
                             "--top-k still win.")
    parser.add_argument("--surface-throttles", action="store_true",
                        help="Disable the azure-cosmos SDK's automatic 429 retry "
                             "(default: 9 attempts, 30s total backoff) so throttled "
                             "requests surface as errors and land in the 'throttled' "
                             "column rather than being absorbed as silent latency. "
                             "Recommended with --ru-stress.")
    parser.add_argument(
        "--only", choices=("cosmos", "atlas", "both"), default="both"
    )
    args = parser.parse_args()

    base_workers, base_top_k = (64, 50) if args.ru_stress else (16, 5)
    workers = args.workers if args.workers is not None else base_workers
    top_k = args.top_k if args.top_k is not None else base_top_k
    if args.ru_stress:
        print(f"[ru-stress] workers={workers} top_k={top_k}")

    settings: Settings = load_settings()
    print(
        f"Embedding {len(CANNED_QUERIES)} canned queries with "
        f"{settings.voyage_model} ({settings.embed_dim}d)..."
    )
    vectors = embed_canned_queries(settings)

    rows = []

    if args.only in ("cosmos", "both"):
        policy = None
        if args.surface_throttles:
            policy = cosmos_documents.ConnectionPolicy()
            policy.RetryOptions = cosmos_documents.RetryOptions(
                max_retry_attempt_count=0,
                fixed_retry_interval_in_milliseconds=0,
                max_wait_time_in_seconds=0,
            )
            print("[surface-throttles] Cosmos SDK auto-retry disabled; "
                  "429s will appear in the 'throttled' column.")
        cosmos = CosmosClient(
            settings.cosmos_endpoint, credential=settings.cosmos_key,
            connection_policy=policy,
        ) if policy else CosmosClient(
            settings.cosmos_endpoint, credential=settings.cosmos_key,
        )
        container = (
            cosmos.get_database_client(settings.cosmos_database)
            .get_container_client(settings.cosmos_container)
        )
        timings, elapsed = _run_load(
            "cosmos",
            workers,
            args.duration,
            lambda v: _cosmos_search(container, v, top_k),
            vectors,
        )
        rows.append(summarise("cosmos", timings, elapsed))

    if args.only in ("atlas", "both"):
        client = MongoClient(settings.mongo_uri, maxPoolSize=max(workers * 2, 32))
        coll = client[settings.mongo_db][settings.mongo_collection]
        timings, elapsed = _run_load(
            "atlas",
            workers,
            args.duration,
            lambda v: _atlas_search(coll, settings.atlas_vector_index, v, top_k),
            vectors,
        )
        rows.append(summarise("atlas", timings, elapsed))

    print()
    print(format_stats_table(rows))
    print()
    print(
        "Notes: 'throttled' counts Cosmos HTTP 429 / TooManyRequests. "
        "Atlas tier limits manifest as connection or timeout errors "
        "rather than 429s, so they land in 'errors' instead."
    )


if __name__ == "__main__":
    main()
