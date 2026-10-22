"""Concurrent read/write load generator for the workload-under-failover cases.

Runs a fixed number of writer and reader threads against a single collection and
reports throughput and latency percentiles in ten-second windows. Windows are
written to JSONL so the report can compare the same metric before, during, and
after a failover rather than averaging the disruption away.

    python3 load_harness.py --profile steady   --duration 900 --label t4
    python3 load_harness.py --profile saturate --duration 600 --label t5

`steady` paces itself at LOAD_TARGET_OPS_PER_SEC. `saturate` removes the pacing
so the cluster becomes the limiting factor — use it only on the test cluster and
only inside an approved window.
"""

from __future__ import annotations

import argparse
import os
import random
import statistics
import threading
import time
from collections import defaultdict

from pymongo import ASCENDING, MongoClient, WriteConcern
from pymongo.errors import PyMongoError

from common import (append_jsonl, artefact_path, load_env, require_env,
                    utc_now)

COLLECTION = "load_events"
WINDOW_SECONDS = 10.0

_lock = threading.Lock()
_samples: dict[str, list[float]] = defaultdict(list)
_errors: dict[str, int] = defaultdict(int)
_stop = threading.Event()


def _record(kind: str, elapsed_ms: float | None, error: str | None) -> None:
    with _lock:
        if error:
            _errors[f"{kind}:{error}"] += 1
        else:
            _samples[kind].append(elapsed_ms or 0.0)


def _writer(coll, pace: float | None) -> None:
    while not _stop.is_set():
        started = time.monotonic()
        try:
            coll.insert_one({
                "ts": utc_now(),
                "shard_hint": random.randint(0, 10_000),
                "amount": round(random.uniform(1, 5_000), 2),
                "payload": "x" * 512,
            })
            _record("write", (time.monotonic() - started) * 1000, None)
        except PyMongoError as exc:
            _record("write", None, type(exc).__name__)
        if pace:
            time.sleep(pace)


def _reader(coll, pace: float | None) -> None:
    while not _stop.is_set():
        started = time.monotonic()
        try:
            key = random.randint(0, 10_000)
            list(coll.find({"shard_hint": key}).limit(20))
            _record("read", (time.monotonic() - started) * 1000, None)
        except PyMongoError as exc:
            _record("read", None, type(exc).__name__)
        if pace:
            time.sleep(pace)


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(fraction * len(ordered)))
    return ordered[index]


def _drain_window() -> dict:
    with _lock:
        samples = {k: v[:] for k, v in _samples.items()}
        errors = dict(_errors)
        _samples.clear()
        _errors.clear()
    window = {"ts": utc_now(), "errors": errors}
    for kind, values in samples.items():
        window[kind] = {
            "ops": len(values),
            "opsPerSec": round(len(values) / WINDOW_SECONDS, 1),
            "p50Ms": round(statistics.median(values), 1) if values else 0.0,
            "p95Ms": round(_percentile(values, 0.95), 1),
            "p99Ms": round(_percentile(values, 0.99), 1),
        }
    return window


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Read/write load harness")
    parser.add_argument("--label", required=True, help="Test case label")
    parser.add_argument("--profile", choices=("steady", "saturate"),
                        default="steady")
    parser.add_argument("--duration", type=int, default=900,
                        help="Run time in seconds (default: 900)")
    args = parser.parse_args()

    uri = require_env("TEST_CLUSTER_URI")
    db_name = os.getenv("TEST_DB", "resilience_test")
    write_workers = int(os.getenv("LOAD_WRITE_WORKERS", "8"))
    read_workers = int(os.getenv("LOAD_READ_WORKERS", "8"))
    target = int(os.getenv("LOAD_TARGET_OPS_PER_SEC", "400"))

    client = MongoClient(uri, retryWrites=True, w="majority")
    coll = client[db_name].get_collection(
        COLLECTION, write_concern=WriteConcern("majority")
    )
    coll.create_index([("shard_hint", ASCENDING)])

    workers = write_workers + read_workers
    pace = None if args.profile == "saturate" else max(0.0, workers / target)

    log = artefact_path(f"load-{args.label}", "jsonl")
    print(f"Load profile : {args.profile}  ({write_workers} writers, "
          f"{read_workers} readers)")
    print(f"Pacing       : {'none (cluster-limited)' if not pace else f'{pace:.3f}s per op'}")
    print(f"Duration     : {args.duration}s")
    print(f"Log          -> {log}\n")

    threads = [threading.Thread(target=_writer, args=(coll, pace), daemon=True)
               for _ in range(write_workers)]
    threads += [threading.Thread(target=_reader, args=(coll, pace), daemon=True)
                for _ in range(read_workers)]
    for thread in threads:
        thread.start()

    deadline = time.monotonic() + args.duration
    try:
        while time.monotonic() < deadline:
            time.sleep(WINDOW_SECONDS)
            window = _drain_window()
            append_jsonl(log, window)
            write = window.get("write", {})
            read = window.get("read", {})
            print(f"  {window['ts']:%H:%M:%S}  "
                  f"w {write.get('opsPerSec', 0):>6}/s p95 {write.get('p95Ms', 0):>7} ms   "
                  f"r {read.get('opsPerSec', 0):>6}/s p95 {read.get('p95Ms', 0):>7} ms   "
                  f"errors {sum(window['errors'].values())}")
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        _stop.set()
        append_jsonl(log, _drain_window())
        client.close()
        print("\nLoad harness stopped.")


if __name__ == "__main__":
    main()
