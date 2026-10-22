#!/usr/bin/env python3
"""Confirm Atlas Search Nodes are serving the demo's Search index.

Run AFTER the operator-performed DSN change (see DSN_RUNBOOK.md).

What this can verify from the client side (normal Atlas connection, no admin
APIs, no direct Search Node connections):
  1. The Search index exists, is READY, and is queryable.
  2. Representative $search queries return results, repeatedly, with latency.
  3. Documented-approach caveat: clients connect via the cluster and cannot see
     which mongot instance served a query. Positive results here confirm the
     index is being served end-to-end; correlate "queries hitting Search
     Nodes" with Atlas UI > Search tab metrics (query latency/throughput charts
     on the Search Nodes) — record those UI numbers per region separately.

Usage:  python confirm_search_nodes.py   (uses the same .env as benchmark.py)
Requires the standard opt-ins since it issues queries (reads only, no writes):
  ATLAS_BENCHMARK_URI must be set. ALLOW_ATLAS_BENCHMARK_WRITES/
  BENCHMARK_CONFIRM are intentionally NOT required because this script is
  read-only and never creates or alters anything.
"""
from __future__ import annotations

import json
import sys
import time

from config import load_config
from generator import query_terms
from metrics import latency_summary, utc_now_iso


def main() -> int:
    cfg = load_config()
    if not cfg.uri:
        sys.exit("ATLAS_BENCHMARK_URI is not set (read-only check, no write gates needed).")
    try:
        from pymongo import MongoClient
    except ImportError:
        sys.exit("pymongo is required: pip install -r requirements.txt")

    client = MongoClient(cfg.uri, appname="atlas-search-index-benchmark-confirm")
    coll = client[cfg.db_name][cfg.collection_name]
    report: dict = {"utc_start": utc_now_iso(), "namespace": cfg.namespace,
                    "search_index_name": cfg.search_index_name,
                    "checks": {}, "cluster_label": cfg.cluster_label}
    try:
        # 1. Index state
        indexes = list(coll.list_search_indexes(cfg.search_index_name))
        if not indexes:
            sys.exit(f"FAIL: index '{cfg.search_index_name}' not found on {cfg.namespace}.")
        idx = indexes[0]
        report["checks"]["index_state"] = {
            "status": idx.get("status"), "queryable": idx.get("queryable"),
            "ok": idx.get("status") == "READY" and bool(idx.get("queryable"))}

        # 2. Representative queries (read-only)
        terms = query_terms(cfg.generator_seed)
        latencies, hits, misses = [], 0, 0
        for term in terms:
            t0 = time.monotonic()
            docs = list(coll.aggregate([
                {"$search": {"index": cfg.search_index_name,
                             "text": {"query": term,
                                      "path": ["title", "summary", "body"]}}},
                {"$limit": 5}], maxTimeMS=10_000))
            latencies.append((time.monotonic() - t0) * 1000)
            if docs:
                hits += 1
            else:
                misses += 1
        report["checks"]["queries"] = {
            "executed": len(terms), "queries_with_hits": hits,
            "queries_with_no_hits": misses,
            "latency_ms": latency_summary(latencies)}

        # 3. Small mixed-query smoke (text + filter path through the index)
        sample = list(coll.aggregate([
            {"$search": {"index": cfg.search_index_name,
                         "compound": {"must": [{"text": {"query": "mongodb", "path": "body"}}],
                                      "filter": [{"term": {"path": "status",
                                                           "query": "active"}}]}}},
            {"$limit": 3}]))
        report["checks"]["compound_query"] = {
            "executed": True, "returned": len(sample)}

        overall = (report["checks"]["index_state"]["ok"] and hits > 0)
        report["verdict"] = ("PASS: index READY/queryable and served $search queries "
                             "successfully end-to-end." if overall else
                             "INCOMPLETE: see checks; confirm in Atlas UI Search tab.")
        report["operator_to_do"] = [
            "Atlas UI > Cluster > Search tab: confirm the index shows the Search Nodes "
            "(tier/topology) and record query metric charts per region.",
            "Record the DSN transition timestamps in results/dsn_transition.md "
            "(e.g., index went on-deck -> READY after the DSN change).",
            "Optionally re-run `python benchmark.py load` and compare with the "
            "pre-DSN baseline.",
        ]
    finally:
        report["utc_end"] = utc_now_iso()
        client.close()
    with open("results/confirm_search_nodes.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
