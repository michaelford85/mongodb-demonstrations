"""Compare the cost of scan-style operations on each backend.

The Cosmos billing model charges request units (RUs) per page read, so
even index-aware queries that touch many documents accumulate RU
proportional to the bytes returned. MongoDB Atlas has no per-operation
billing unit; the comparable signal there is latency. We measure both
and print them side-by-side for two scan-style operations:

  1. Total document count.
  2. Project _id (or equivalent) for every chunk.

Run against the dual-loaded chunks collection produced earlier in the
pipeline.

Usage:
    python -m compare.full_scan
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from azure.cosmos import CosmosClient
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import load_settings  # noqa: E402

RU_HEADER = "x-ms-request-charge"


@dataclass
class ScanResult:
    backend: str
    operation: str
    items: int
    latency_ms: float
    ru: float | None  # None when the concept doesn't apply (Atlas)


def _cosmos_count(container) -> ScanResult:
    started = time.perf_counter()
    pager = container.query_items(
        query="SELECT VALUE COUNT(1) FROM c",
        enable_cross_partition_query=True,
    ).by_page()
    total = 0
    ru = 0.0
    for page in pager:
        for value in page:
            total += int(value)
        headers = container.client_connection.last_response_headers
        ru += float(headers.get(RU_HEADER, 0.0) or 0.0)
    return ScanResult(
        "cosmos", "count", total, (time.perf_counter() - started) * 1000.0, ru
    )


def _cosmos_project_ids(container) -> ScanResult:
    started = time.perf_counter()
    pager = container.query_items(
        query="SELECT c.id FROM c",
        enable_cross_partition_query=True,
    ).by_page()
    items = 0
    ru = 0.0
    for page in pager:
        items += sum(1 for _ in page)
        headers = container.client_connection.last_response_headers
        ru += float(headers.get(RU_HEADER, 0.0) or 0.0)
    return ScanResult(
        "cosmos", "project _id", items, (time.perf_counter() - started) * 1000.0, ru
    )


def _atlas_count(coll) -> ScanResult:
    started = time.perf_counter()
    total = coll.estimated_document_count()
    return ScanResult(
        "atlas", "count", total, (time.perf_counter() - started) * 1000.0, None
    )


def _atlas_project_ids(coll) -> ScanResult:
    started = time.perf_counter()
    items = 0
    for _ in coll.find({}, {"_id": 1}).batch_size(1000):
        items += 1
    return ScanResult(
        "atlas", "project _id", items, (time.perf_counter() - started) * 1000.0, None
    )


def _row(result: ScanResult) -> tuple[str, ...]:
    ru = f"{result.ru:.1f}" if result.ru is not None else "n/a"
    return (
        result.backend,
        result.operation,
        f"{result.items}",
        f"{result.latency_ms:.0f}",
        ru,
    )


def _print_table(rows: list[tuple[str, ...]]) -> None:
    header = ("backend", "operation", "items", "ms", "RU")
    all_rows = [header] + rows
    widths = [max(len(r[i]) for r in all_rows) for i in range(len(header))]
    sep = "  ".join("-" * w for w in widths)
    print("  ".join(name.ljust(w) for name, w in zip(header, widths)))
    print(sep)
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("cosmos", "atlas", "both"), default="both")
    args = parser.parse_args()
    settings = load_settings()

    results: list[ScanResult] = []

    if args.only in ("cosmos", "both"):
        cosmos = CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
        container = (
            cosmos.get_database_client(settings.cosmos_database)
            .get_container_client(settings.cosmos_container)
        )
        results.append(_cosmos_count(container))
        results.append(_cosmos_project_ids(container))

    if args.only in ("atlas", "both"):
        client = MongoClient(settings.mongo_uri)
        coll = client[settings.mongo_db][settings.mongo_collection]
        results.append(_atlas_count(coll))
        results.append(_atlas_project_ids(coll))

    print()
    _print_table([_row(r) for r in results])
    print()
    print(
        "Cosmos pages cost RU proportional to bytes scanned, so even a "
        "covered count or _id projection accumulates RU as the chunk set "
        "grows. Atlas count_documents (and a projection-only find) have "
        "no comparable per-page billing unit."
    )


if __name__ == "__main__":
    main()
