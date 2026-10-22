#!/usr/bin/env python3
"""Atlas Search index-build / readiness / search-load benchmark.

Plan-only by default. Every phase that touches Atlas requires:
  ATLAS_BENCHMARK_URI + ALLOW_ATLAS_BENCHMARK_WRITES=true + BENCHMARK_CONFIRM=yes

Phases:
  plan     Validate config and print the plan (no writes). DEFAULT.
  seed     Seed the demo collection with deterministic synthetic documents.
  index    Create the Search index (if absent) and poll to verified readiness.
  load     Run the search-load profile; report offered vs achieved QPS + latency.
  mixed    Search load + optional capped write churn (opt-in).
  cleanup  Preview and (after confirmation) drop ONLY the demo collection/index.

This demo never calls Atlas admin APIs and never changes cluster/topology.
It does NOT measure the Dedicated Search Node (DSN) transition — see
DSN_RUNBOOK.md for the operator-timed procedure.
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import time

from config import HARD_LIMITS, load_config, summarize
from generator import iter_documents, query_terms
from metrics import latency_summary, save_results, utc_now_iso
from safety import (WARNING, cleanup_preview, interactive_confirm,
                    sanitized_target, sha256_file, write_gate_check)

STOP = threading.Event()


def _install_sigint():
    def handler(signum, frame):
        print("\nInterrupt received: stopping generators cleanly...", flush=True)
        STOP.set()
    signal.signal(signal.SIGINT, handler)


def _connect(cfg):
    try:
        from pymongo import MongoClient
    except ImportError:
        sys.exit("pymongo is required for live phases: pip install -r requirements.txt")
    client = MongoClient(cfg.uri, appname="atlas-search-index-benchmark")
    coll = client[cfg.db_name][cfg.collection_name]
    return client, coll


def _index_definition(cfg) -> dict:
    if cfg.index_definition_file:
        with open(cfg.index_definition_file, "r", encoding="utf-8") as fh:
            return json.load(fh)
    with open("search_index.default.json", "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- phases ----

def phase_plan(cfg) -> dict:
    plan = summarize(cfg)
    ok, reasons = write_gate_check(cfg)
    plan["will_write_anything"] = bool(cfg.live_allowed)
    plan["gate_status"] = "OPEN (live actions possible)" if ok else "CLOSED (plan-only)"
    plan["closed_reasons"] = reasons
    print(WARNING)
    print(json.dumps(plan, indent=2, default=str))
    if plan["problems"]:
        print("\nCONFIG PROBLEMS — refuse to run live phases until fixed.")
    return plan


def phase_seed(cfg) -> dict:
    if not interactive_confirm(sanitized_target(cfg.uri), cfg.namespace, "seed", cfg):
        return {"status": "blocked", "reasons": write_gate_check(cfg)[1]}
    client, coll = _connect(cfg)
    result = {"status": "started", "doc_count_target": cfg.doc_count,
              "utc_start": utc_now_iso(), "inserted": 0, "errors": 0, "batches": 0}
    start = time.monotonic()
    try:
        # Resumable: skip sequences whose _id already exists.
        existing = set(coll.find({"_id": {"$regex": r"^bench-"}}, {"_id": 1})
                       .distinct("_id")) if cfg.doc_count <= 100_000 else None
        start_seq = 0
        if existing:
            for seq in range(cfg.doc_count):
                if f"bench-{seq:08d}" in existing:
                    start_seq = seq + 1
        result["resumed_from_seq"] = start_seq
        batch, inserted = [], 0
        for doc in iter_documents(cfg.doc_count - start_seq, cfg.generator_seed,
                                  start=start_seq):
            if STOP.is_set():
                result["status"] = "interrupted"
                break
            batch.append(doc)
            if len(batch) >= cfg.batch_size:
                coll.insert_many(batch, ordered=False)
                inserted += len(batch)
                result["batches"] += 1
                print(f"  seeded {inserted}/{cfg.doc_count}", flush=True)
                batch = []
        if batch:
            coll.insert_many(batch, ordered=False)
            inserted += len(batch)
            result["batches"] += 1
        result["inserted"] = inserted
        result["confirmed_count"] = coll.count_documents({})
        elapsed = time.monotonic() - start
        result["elapsed_seconds"] = round(elapsed, 2)
        result["docs_per_second"] = round(inserted / elapsed, 1) if elapsed else None
        if result["status"] == "started":
            result["status"] = "completed"
    finally:
        result["utc_end"] = utc_now_iso()
        client.close()
    return result


def phase_index(cfg) -> dict:
    if not interactive_confirm(sanitized_target(cfg.uri), cfg.namespace,
                               "create Search index (if absent)", cfg):
        return {"status": "blocked", "reasons": write_gate_check(cfg)[1]}
    from pymongo.operations import SearchIndexModel

    client, coll = _connect(cfg)
    definition = _index_definition(cfg)
    result = {"status": "started", "utc_start": utc_now_iso(),
              "index_name": cfg.search_index_name,
              "definition_file": cfg.index_definition_file or "search_index.default.json",
              "definition_hash": sha256_file(
                  cfg.index_definition_file or "search_index.default.json"),
              "warning": "default definition is an illustrative lexical mapping, "
                         "not equivalent to any production mapping",
              "state_transitions": []}
    try:
        existing = list(coll.list_search_indexes(cfg.search_index_name))
        if existing:
            result["created"] = False
            result["state_transitions"].append(
                {"state": existing[0].get("status"), "note": "index already existed"})
            index_model = None
        else:
            index_model = SearchIndexModel(
                definition=definition.get("definition", definition),
                name=cfg.search_index_name,
                type="search")
        create_requested = time.monotonic()
        if index_model is not None:
            coll.create_search_index(index_model)
            result["created"] = True
            result["create_request_seconds"] = round(time.monotonic() - create_requested, 3)

        # Poll until queryable + verified by a representative query.
        deadline = time.monotonic() + cfg.index_ready_timeout_seconds
        last_state = None
        queryable = False
        while time.monotonic() < deadline and not STOP.is_set():
            docs = list(coll.list_search_indexes(cfg.search_index_name))
            status = docs[0].get("status") if docs else "NOT_FOUND"
            queryable = bool(docs and docs[0].get("queryable"))
            if status != last_state:
                result["state_transitions"].append(
                    {"utc": utc_now_iso(), "status": status, "queryable": queryable})
                print(f"  index status: {status} queryable={queryable}", flush=True)
                last_state = status
            if status == "READY" and queryable:
                probe = list(coll.aggregate([
                    {"$search": {"index": cfg.search_index_name,
                                 "text": {"query": "mongodb", "path": "title"}}},
                    {"$limit": 1}]))
                if probe:
                    result["verified_queryable"] = True
                    result["status"] = "ready"
                    break
            time.sleep(cfg.poll_interval_seconds)
        else:
            result["status"] = "timeout_or_interrupted"
        result["create_to_verified_ready_seconds"] = round(
            time.monotonic() - create_requested, 2)
        result["poll_interval_seconds"] = cfg.poll_interval_seconds
        result["note_index_size"] = (
            "Search index size is not exposed via this driver API. Record it from "
            "Atlas UI: Cluster > Search tab > index metrics (do NOT confuse with "
            "collection storage size).")
    finally:
        result["utc_end"] = utc_now_iso()
        client.close()
    return result


def _run_load(cfg, with_writes: bool) -> dict:
    ok, reasons = write_gate_check(cfg)
    if not ok:
        return {"status": "blocked", "reasons": reasons}
    client, coll = _connect(cfg)
    try:
        indexes = list(coll.list_search_indexes(cfg.search_index_name))
        if not indexes:
            return {"status": "refused",
                    "reason": f"Search index '{cfg.search_index_name}' does not exist on "
                              f"{cfg.namespace}. Run `python benchmark.py index` first."}
        if not (indexes[0].get("status") == "READY" and indexes[0].get("queryable")):
            return {"status": "refused",
                    "reason": f"Search index '{cfg.search_index_name}' is not READY/"
                              f"queryable (state: {indexes[0].get('status')}). "
                              "Run `python benchmark.py index` first."}
    except Exception as exc:
        return {"status": "refused", "reason": f"cannot verify Search index: {exc}"}
    terms = query_terms(cfg.generator_seed)
    result = {"status": "started", "utc_start": utc_now_iso(),
              "offered_qps": cfg.qps, "profile_label": summarize(cfg)["search_load"]["profile_label"],
              "concurrency": cfg.concurrency, "success": 0, "errors": 0, "timeouts": 0}
    lock = threading.Lock()
    latencies: list[float] = []
    op_counts = {"success": 0, "errors": 0, "timeouts": 0}
    error_samples: dict[str, int] = {}

    def record_error(exc: Exception):
        key = str(exc).split("full error", 1)[0][:160]
        with lock:
            op_counts["errors"] += 1
            error_samples[key] = error_samples.get(key, 0) + 1

    def search_worker():
        idx = 0
        while not STOP.is_set():
            term = terms[idx % len(terms)]
            idx += 1
            t0 = time.monotonic()
            try:
                list(coll.aggregate([
                    {"$search": {"index": cfg.search_index_name,
                                 "text": {"query": term, "path": ["title", "summary", "body"]}}},
                    {"$limit": 10}], maxTimeMS=int(cfg.query_timeout_seconds * 1000)))
                dt_ms = (time.monotonic() - t0) * 1000
                with lock:
                    latencies.append(dt_ms)
                    op_counts["success"] += 1
            except Exception as exc:
                with lock:
                    if "timed out" in str(exc).lower() or "MaxTimeMS" in str(exc):
                        op_counts["timeouts"] += 1
                    else:
                        record_error(exc)
            # QPS pacing shared across workers.
            slot_sleep = cfg.concurrency / max(cfg.qps, 0.001)
            stop_at = time.monotonic() + slot_sleep
            while not STOP.is_set():
                remaining = stop_at - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(0.05, remaining))

    def write_worker(kind: str, rate: float):
        interval = cfg.concurrency / rate if rate else 1
        while not STOP.is_set():
            try:
                if kind == "insert":
                    doc = next(iter_documents(1, cfg.generator_seed,
                                              start=int(time.time())))
                    coll.insert_one(doc)
                elif kind == "update":
                    coll.update_one({"status": "pending"},
                                    {"$inc": {"views": 1}})
                elif kind == "delete":
                    coll.delete_one({"status": "archived"})
            except Exception:
                with lock:
                    op_counts["errors"] += 1
            stop_at = time.monotonic() + interval
            while not STOP.is_set():
                remaining = stop_at - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(0.05, remaining))

    warmup_done = time.monotonic() + cfg.warmup_seconds
    load_end = warmup_done + cfg.duration_seconds
    result["warmup_seconds"] = cfg.warmup_seconds
    result["steady_state_seconds"] = cfg.duration_seconds
    threads = []
    try:
        if cfg.warmup_seconds > 0:
            result["phase"] = "warmup"
        for _ in range(cfg.concurrency):
            t = threading.Thread(target=search_worker, daemon=True)
            threads.append(t)
            t.start()
        if with_writes and cfg.mixed_enabled:
            for kind, rate in (("insert", cfg.insert_per_sec),
                               ("update", cfg.update_per_sec),
                               ("delete", cfg.delete_per_sec)):
                if rate > 0:
                    threads.append(threading.Thread(
                        target=write_worker, args=(kind, rate), daemon=True))
                    threads[-1].start()
        while time.monotonic() < load_end and not STOP.is_set():
            time.sleep(0.25)
        STOP.set()
        for t in threads:
            t.join(timeout=5)
        result["status"] = "completed" if not result.get("phase") else "completed"
        with lock:
            result.update(op_counts)
            result["latency_ms"] = latency_summary(latencies)
            result["error_samples"] = error_samples
        elapsed = cfg.warmup_seconds + cfg.duration_seconds
        achieved = result["success"] / elapsed if elapsed > 0 else None
        result["achieved_qps"] = round(achieved, 2) if achieved else None
        result["offered_vs_achieved_note"] = (
            "offered QPS is the configured pacing target; achieved QPS counts "
            "successful queries over warm-up + steady-state wall time")
        result["note"] = ("latency_ms measures client-side Atlas Search query "
                          "round-trip via the normal cluster connection; it is not "
                          "a Search-Node-internal metric")
    finally:
        STOP.clear()
        result["utc_end"] = utc_now_iso()
        client.close()
    return result


def phase_load(cfg) -> dict:
    return _run_load(cfg, with_writes=False)


def phase_mixed(cfg) -> dict:
    if not cfg.mixed_enabled:
        return {"status": "skipped",
                "reason": "write rates default to 0; opt in via MIXED_*_PER_SEC env vars"}
    if cfg.insert_per_sec > HARD_LIMITS["max_insert_per_sec"]:
        return {"status": "refused", "reason": "insert rate over hard cap"}
    return _run_load(cfg, with_writes=True)


def phase_cleanup(cfg) -> dict:
    preview = cleanup_preview(cfg.namespace, cfg.search_index_name)
    print(json.dumps(preview, indent=2))
    if not interactive_confirm(sanitized_target(cfg.uri), cfg.namespace, "cleanup", cfg):
        return {"status": "blocked", "reasons": write_gate_check(cfg)[1]}
    client, coll = _connect(cfg)
    try:
        coll.drop_search_index(cfg.search_index_name)
        coll.drop()
        return {"status": "completed", **preview, "utc_end": utc_now_iso()}
    finally:
        client.close()


PHASES = {"plan": phase_plan, "seed": phase_seed, "index": phase_index,
          "load": phase_load, "mixed": phase_mixed, "cleanup": phase_cleanup}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=sorted(PHASES), nargs="?", default="plan")
    args = parser.parse_args()
    cfg = load_config()
    _install_sigint()
    result = PHASES[args.phase](cfg)
    result["run_id"] = f"{args.phase}-{int(time.time())}"
    result["utc_start"] = result.get("utc_start", utc_now_iso())
    result["utc_end"] = result.get("utc_end", utc_now_iso())
    result["namespace"] = cfg.namespace
    result["cluster_label"] = cfg.cluster_label
    result["search_index_name"] = cfg.search_index_name
    result["runtime"] = {"python": sys.version.split()[0]}
    result["warnings"] = [
        "Planning inputs (index KB/doc, 100 QPS, 2000/2000/500 write ops/sec) are "
        "unverified estimates, not measured production telemetry.",
        "This demo does not measure the Atlas-side Dedicated Search Node (DSN) "
        "transition; see DSN_RUNBOOK.md.",
    ]
    result["operator_recorded"] = [
        "Search index size: Atlas UI > Cluster > Search tab index metrics "
        "(not collection storage size).",
        "Search Node CPU/storage: Atlas UI or supported monitoring, per region.",
        "Index freshness/lag: Atlas UI Search index metrics, if available.",
    ]
    if args.phase != "plan":
        json_path, md_path = save_results(result, "results", result["run_id"])
        print(f"Results written: {json_path}, {md_path}")
        print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
