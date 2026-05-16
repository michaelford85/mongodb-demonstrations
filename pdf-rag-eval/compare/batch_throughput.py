"""Batch write + concurrent vector-query throughput on each backend.

Write phase: generate --rows synthetic chunk documents (matching the
catalog schema) and insert them into each backend using the largest bulk
operation each SDK supports — insert_many on pymongo, parallel
upsert_item on azure-cosmos. Documents land in the existing namespace
under a 'bench_' chunk_id prefix so the existing vector indexes can be
used for the query phase. Bench docs are deleted at the end.

Query phase: --duration seconds of concurrent vector-search queries with
random embeddings against the same index/container. Watch throttled and
retry counts climb on Cosmos as --rows grows past what the autoscale
RU/s ceiling can absorb.

By default the azure-cosmos SDK auto-retries 429s up to 9 times with 30s
of total backoff, so a saturated container shows up as inflated latency
and the 'throttled' / 'retries' columns stay near zero. --surface-throttles
disables that SDK-side auto-retry so 429s reach the application loop and
land in the 'throttled' column (the in-script bounded retry on writes
still applies, so 'retries' also populates honestly).

Usage:
    python -m compare.batch_throughput --rows 10000 --workers 8 --duration 30
    python -m compare.batch_throughput --rows 50000 --only atlas
    python -m compare.batch_throughput --rows 10000 --surface-throttles
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from azure.cosmos import CosmosClient
from azure.cosmos import documents as cosmos_documents
from azure.cosmos.exceptions import CosmosHttpResponseError
from pymongo import MongoClient
from pymongo.errors import BulkWriteError, PyMongoError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compare.common import _looks_throttled  # noqa: E402
from config import Settings, load_settings  # noqa: E402

BENCH_PREFIX = "bench_"
ATLAS_WRITE_BATCH = 1000           # pymongo insert_many splits at ~100KB internally
COSMOS_WRITE_RETRIES = 5           # bounded retry on 429 so the bench can complete
VECTOR_POOL_SIZE = 64              # number of unique random vectors to rotate through


@dataclass
class Phase:
    label: str            # "write" / "query"
    ops: int              # successful operations
    elapsed_s: float
    throttled: int = 0    # Cosmos 429s observed
    retries: int = 0      # total retry attempts made
    errors: int = 0       # non-throttle failures


def _gen_chunk(i: int, dim: int, vec_pool: list[list[float]]) -> dict:
    # 5 chunks per synthetic document spreads writes across logical partitions.
    doc_id = f"bench{i // 5:08d}"
    return {
        "chunk_id": f"{BENCH_PREFIX}{i:09d}",
        "document_id": doc_id,
        "blob_path": "catalog/spec-bench.pdf",
        "blob_url": "https://example.invalid/pdfs/catalog/spec-bench.pdf",
        "filename": "spec-bench.pdf",
        "title": "Product Specification Sheet: Benchmark",
        "vendor": "Benchmark Co",
        "category": "storage-hardware",
        "item_id": "BCH-00000-A",
        "revision": "2026-01-01",
        "page_number": 1,
        "chunk_index": i % 5,
        "text": "synthetic benchmark chunk",
        "embedding": vec_pool[i % len(vec_pool)],
    }


def _vector_pool(dim: int, size: int = VECTOR_POOL_SIZE) -> list[list[float]]:
    rng = random.Random(20260512)
    return [[rng.gauss(0.0, 1.0) for _ in range(dim)] for _ in range(size)]


# --- Cosmos -----------------------------------------------------------------

def _cosmos_write_one(container, doc: dict, counters: Phase) -> bool:
    delay = 0.1
    for attempt in range(COSMOS_WRITE_RETRIES + 1):
        try:
            # Cosmos id field mirrors chunk_id; everything else is a regular field.
            item = {"id": doc["chunk_id"], **{k: v for k, v in doc.items() if k != "chunk_id"}}
            container.upsert_item(item)
            return True
        except CosmosHttpResponseError as exc:
            if exc.status_code == 429 or _looks_throttled(str(exc)):
                counters.throttled += 1
                if attempt < COSMOS_WRITE_RETRIES:
                    counters.retries += 1
                    time.sleep(delay)
                    delay = min(delay * 2.0, 5.0)
                    continue
            counters.errors += 1
            return False
    counters.errors += 1
    return False


def _cosmos_write(container, docs: list[dict], workers: int) -> Phase:
    phase = Phase("cosmos write", ops=0, elapsed_s=0.0)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_cosmos_write_one, container, d, phase) for d in docs]
        for fut in as_completed(futures):
            if fut.result():
                phase.ops += 1
    phase.elapsed_s = time.perf_counter() - started
    return phase


def _cosmos_query_loop(container, vec_pool: list[list[float]], deadline: float,
                      phase: Phase) -> None:
    rng = random.Random()
    while time.perf_counter() < deadline:
        vec = vec_pool[rng.randrange(len(vec_pool))]
        try:
            list(container.query_items(
                query=("SELECT TOP 5 c.id, VectorDistance(c.embedding, @v) AS s "
                       "FROM c ORDER BY VectorDistance(c.embedding, @v)"),
                parameters=[{"name": "@v", "value": vec}],
                enable_cross_partition_query=True,
            ))
            phase.ops += 1
        except CosmosHttpResponseError as exc:
            if exc.status_code == 429 or _looks_throttled(str(exc)):
                phase.throttled += 1
            else:
                phase.errors += 1


def _cosmos_cleanup(container, doc_count: int) -> None:
    # Delete by id+partition_key. Chunks 0..N-1 group into documents bench00000000..
    for i in range(doc_count):
        cid = f"{BENCH_PREFIX}{i:09d}"
        pk = f"bench{i // 5:08d}"
        try:
            container.delete_item(item=cid, partition_key=pk)
        except CosmosHttpResponseError:
            pass


# --- Atlas ------------------------------------------------------------------

def _atlas_write(coll, docs: list[dict]) -> Phase:
    phase = Phase("atlas write", ops=0, elapsed_s=0.0)
    started = time.perf_counter()
    # _id mirrors chunk_id; pymongo splits insert_many into wire-protocol batches.
    payload = [{"_id": d["chunk_id"], **{k: v for k, v in d.items() if k != "chunk_id"}}
               for d in docs]
    for i in range(0, len(payload), ATLAS_WRITE_BATCH):
        batch = payload[i : i + ATLAS_WRITE_BATCH]
        try:
            coll.insert_many(batch, ordered=False)
            phase.ops += len(batch)
        except BulkWriteError as exc:
            phase.ops += exc.details.get("nInserted", 0)
            phase.errors += len(batch) - exc.details.get("nInserted", 0)
        except PyMongoError:
            phase.errors += len(batch)
    phase.elapsed_s = time.perf_counter() - started
    return phase


def _atlas_query_loop(coll, index_name: str, vec_pool: list[list[float]],
                      deadline: float, phase: Phase) -> None:
    rng = random.Random()
    while time.perf_counter() < deadline:
        vec = vec_pool[rng.randrange(len(vec_pool))]
        try:
            list(coll.aggregate([
                {"$vectorSearch": {
                    "index": index_name, "path": "embedding",
                    "queryVector": vec, "numCandidates": 50, "limit": 5,
                }},
                {"$project": {"_id": 1, "score": {"$meta": "vectorSearchScore"}}},
            ]))
            phase.ops += 1
        except PyMongoError:
            phase.errors += 1


def _atlas_cleanup(coll) -> None:
    coll.delete_many({"_id": {"$regex": f"^{BENCH_PREFIX}"}})


# --- Driver -----------------------------------------------------------------

def _query_phase(label: str, workers: int, duration_s: float,
                 loop_fn) -> Phase:
    phase = Phase(label, ops=0, elapsed_s=0.0)
    deadline = time.perf_counter() + duration_s
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(loop_fn, deadline, phase) for _ in range(workers)]
        for fut in as_completed(futures):
            fut.result()
    phase.elapsed_s = time.perf_counter() - started
    return phase


def _print_table(rows: list[tuple[str, ...]]) -> None:
    header = ("backend", "phase", "ops", "elapsed s", "ops/s", "throttled", "retries", "errors")
    all_rows = [header] + rows
    widths = [max(len(r[i]) for r in all_rows) for i in range(len(header))]
    print("  ".join(name.ljust(w) for name, w in zip(header, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))


def _row(backend: str, phase: Phase) -> tuple[str, ...]:
    rate = phase.ops / phase.elapsed_s if phase.elapsed_s > 0 else 0.0
    return (
        backend, phase.label.split(" ", 1)[1],
        f"{phase.ops}", f"{phase.elapsed_s:.1f}", f"{rate:.1f}",
        f"{phase.throttled}", f"{phase.retries}", f"{phase.errors}",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=10000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--only", choices=("cosmos", "atlas", "both"), default="both")
    parser.add_argument("--surface-throttles", action="store_true",
                        help="Disable the azure-cosmos SDK's automatic 429 retry "
                             "(default: 9 attempts, 30s total backoff) so throttled "
                             "requests surface to the application loop and land in "
                             "the 'throttled' column rather than being absorbed as "
                             "silent latency.")
    args = parser.parse_args()
    settings: Settings = load_settings()

    print(f"Generating {args.rows} synthetic chunks (dim={settings.embed_dim})...")
    vec_pool = _vector_pool(settings.embed_dim)
    docs = [_gen_chunk(i, settings.embed_dim, vec_pool) for i in range(args.rows)]
    rows: list[tuple[str, ...]] = []

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
        container = (cosmos.get_database_client(settings.cosmos_database)
                     .get_container_client(settings.cosmos_container))
        print(f"[cosmos] write phase: {args.rows} rows / {args.workers} workers...")
        wphase = _cosmos_write(container, docs, args.workers)
        rows.append(_row("cosmos", wphase))
        print(f"[cosmos] query phase: {args.duration}s / {args.workers} workers...")
        qphase = _query_phase("cosmos query", args.workers, args.duration,
                              lambda d, p: _cosmos_query_loop(container, vec_pool, d, p))
        rows.append(_row("cosmos", qphase))
        print("[cosmos] cleaning up bench docs...")
        _cosmos_cleanup(container, args.rows)

    if args.only in ("atlas", "both"):
        client = MongoClient(settings.mongo_uri,
                             maxPoolSize=max(args.workers * 2, 32))
        coll = client[settings.mongo_db][settings.mongo_collection]
        print(f"[atlas] write phase: {args.rows} rows (insert_many batches of {ATLAS_WRITE_BATCH})...")
        wphase = _atlas_write(coll, docs)
        rows.append(_row("atlas", wphase))
        print(f"[atlas] query phase: {args.duration}s / {args.workers} workers...")
        qphase = _query_phase("atlas query", args.workers, args.duration,
                              lambda d, p: _atlas_query_loop(coll, settings.atlas_vector_index, vec_pool, d, p))
        rows.append(_row("atlas", qphase))
        print("[atlas] cleaning up bench docs...")
        _atlas_cleanup(coll)

    print()
    _print_table(rows)
    print()
    print("Cosmos throttled / retries counters surface 429s observed by the "
          "driver. Atlas vector search isn't billed per request, so concurrency "
          "is gated by tier connection limits which appear as errors instead.")


if __name__ == "__main__":
    main()
