"""Show why you match the index to the regime instead of forcing one on all.

For each LARGE tenant this runs the SAME query two ways over the SAME vectors:

  * FLAT  — the shared flat index on the base collection, filtered to the
            tenant. Exact, but an exhaustive scan of a large partition.
  * HNSW  — the tenant's dedicated HNSW view. Approximate graph search.

It reports median latency for both and the top-k overlap (HNSW recall vs the
exact flat result). The takeaway: flat is cheap and exact for the small
partitions, but large partitions want HNSW — one index does not fit every
regime.

    python scripts/benchmark.py --profile demo --iterations 20
"""
import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import tenants  # noqa: E402
from lib.router import Route, build_pipeline  # noqa: E402
from lib.client import (  # noqa: E402
    get_collection, get_db, view_name, COLLECTION_NAME,
    FLAT_INDEX, HNSW_INDEX, PROFILE, QUERY_LIMIT,
)
from lib.embeddings import embed_query  # noqa: E402

_QUERY = "customer cannot sign in after multi-factor authentication reset"


def _time_pipeline(target, pipeline, iterations: int) -> tuple:
    target.aggregate(pipeline)  # warm up
    timings, last = [], []
    for _ in range(iterations):
        start = time.perf_counter()
        last = list(target.aggregate(pipeline))
        timings.append((time.perf_counter() - start) * 1000.0)
    return statistics.median(timings), last


def _overlap(a: list, b: list) -> float:
    sa = {d["doc_id"] for d in a}
    sb = {d["doc_id"] for d in b}
    return len(sa & sb) / len(sa) if sa else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Flat vs HNSW regime benchmark.")
    parser.add_argument("--profile", default=PROFILE, choices=list(tenants.PROFILES))
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--limit", type=int, default=QUERY_LIMIT)
    parser.add_argument("--fake-embeddings", action="store_true")
    args = parser.parse_args()

    vector = embed_query(_QUERY, fake=args.fake_embeddings)
    coll = get_collection()
    db = get_db()

    print(f"Query: {_QUERY!r}   (median of {args.iterations} runs, "
          f"top {args.limit})\n")
    header = f"  {'tenant':<12}{'flat (ms)':>12}{'hnsw (ms)':>12}{'hnsw recall':>14}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for tid in tenants.large_tenant_ids(args.profile):
        flat_route = Route("flat", COLLECTION_NAME, FLAT_INDEX, tid)
        hnsw_route = Route("hnsw", view_name(tid), HNSW_INDEX, tid)
        flat_ms, flat_hits = _time_pipeline(
            coll, build_pipeline(vector, flat_route, args.limit), args.iterations)
        hnsw_ms, hnsw_hits = _time_pipeline(
            db[view_name(tid)], build_pipeline(vector, hnsw_route, args.limit),
            args.iterations)
        recall = _overlap(flat_hits, hnsw_hits)
        print(f"  {tid:<12}{flat_ms:>12.1f}{hnsw_ms:>12.1f}{recall:>13.0%}")

    print("\nFlat is exact (the recall baseline); HNSW trades a little recall for "
          "lower latency as the partition grows. Small tenants stay on flat.")


if __name__ == "__main__":
    main()
