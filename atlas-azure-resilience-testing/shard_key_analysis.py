"""Evaluate candidate shard keys against real query traffic.

`analyzeShardKey` reports cardinality, frequency and monotonicity for a
candidate key, and — only when `configureQueryAnalyzer` has been sampling the
namespace — read and write distribution. Without sampling, the distribution
fields come back as zeros, so this script can enable sampling, wait, and then
analyse.

    # start sampling (run first, leave the workload running)
    python3 shard_key_analysis.py --namespace resilience_test.load_events \
        --enable-sampling --sample-rate 5

    # after at least 15-30 min of representative traffic
    python3 shard_key_analysis.py --namespace resilience_test.load_events \
        --key shard_hint:hashed --key shard_hint:1,ts:1

    # stop sampling when finished
    python3 shard_key_analysis.py --namespace resilience_test.load_events \
        --disable-sampling

Runs against an unsharded replica set as well, which is the point: the keys can
be evaluated before any decision to shard is made.
"""

from __future__ import annotations

import argparse

from pymongo import MongoClient
from pymongo.errors import OperationFailure

from common import artefact_path, load_env, scoped_uri, utc_now, write_json


def parse_key(spec: str) -> dict:
    """Turn 'field:hashed,other:1' into {'field': 'hashed', 'other': 1}."""
    key: dict = {}
    for part in spec.split(","):
        field, _, direction = part.partition(":")
        field = field.strip()
        direction = direction.strip() or "1"
        key[field] = direction if direction == "hashed" else int(direction)
    return key


def summarise(namespace: str, key: dict, result: dict) -> None:
    print(f"\n  namespace : {namespace}")
    print(f"  key       : {key}")

    cardinality = result.get("keyCharacteristics", {})
    if cardinality:
        print(f"  distinct values      : {cardinality.get('numDistinctValues')}")
        print(f"  documents sampled    : {cardinality.get('numDocsSampled')}")
        print(f"  monotonically changing: {cardinality.get('monotonicity', {}).get('recordIdCorrelationCoefficient')}")
        most = cardinality.get("mostCommonValues") or []
        if most:
            top = most[0]
            print(f"  most common value    : {top.get('frequency')} occurrences")

    reads = result.get("readDistribution", {})
    writes = result.get("writeDistribution", {})
    if reads.get("sampleSize", {}).get("total"):
        print(f"  reads targeting one shard   : "
              f"{reads.get('percentageOfSingleShardReads')}%")
        print(f"  reads hitting many shards   : "
              f"{reads.get('percentageOfMultiShardReads')}%")
        print(f"  scatter-gather reads        : "
              f"{reads.get('percentageOfScatterGatherReads')}%")
    else:
        print("  read distribution    : no samples "
              "(configureQueryAnalyzer not sampling long enough)")

    if writes.get("sampleSize", {}).get("total"):
        print(f"  writes targeting one shard  : "
              f"{writes.get('percentageOfSingleShardWrites')}%")
        print(f"  shard-key updates           : "
              f"{writes.get('percentageOfShardKeyUpdates')}%")
    else:
        print("  write distribution   : no samples")


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Shard key candidate analysis")
    parser.add_argument("--namespace", required=True, help="db.collection")
    parser.add_argument("--key", action="append", default=[],
                        help="Candidate key, e.g. 'customer_id:hashed'. Repeatable.")
    parser.add_argument("--enable-sampling", action="store_true",
                        help="Turn on configureQueryAnalyzer for the namespace")
    parser.add_argument("--disable-sampling", action="store_true",
                        help="Turn off configureQueryAnalyzer for the namespace")
    parser.add_argument("--sample-rate", type=float, default=5.0,
                        help="Sampled queries per second when enabling (default: 5)")
    args = parser.parse_args()

    # configureQueryAnalyzer and analyzeShardKey need atlasAdmin.
    client = MongoClient(scoped_uri("ADMIN_CLUSTER_URI"))
    admin = client.admin

    try:
        if args.enable_sampling:
            admin.command("configureQueryAnalyzer", args.namespace,
                          mode="full", samplesPerSecond=args.sample_rate)
            print(f"Sampling enabled on {args.namespace} at "
                  f"{args.sample_rate} samples/s. Leave the workload running, "
                  f"then re-run with --key.")
            return

        if args.disable_sampling:
            admin.command("configureQueryAnalyzer", args.namespace, mode="off")
            print(f"Sampling disabled on {args.namespace}.")
            return

        if not args.key:
            raise SystemExit("Pass at least one --key, or --enable-sampling.")

        analyses = []
        for spec in args.key:
            key = parse_key(spec)
            try:
                result = admin.command("analyzeShardKey", args.namespace, key=key)
            except OperationFailure as exc:
                print(f"\n  key {key}: analyzeShardKey failed "
                      f"(code {exc.code}) — {exc.details.get('codeName') if exc.details else ''}")
                analyses.append({"key": key, "error": exc.code})
                continue
            summarise(args.namespace, key, result)
            analyses.append({"key": key, "result": result})
        print()

        write_json(
            artefact_path("shard-key-analysis", "json"),
            {"capturedAt": utc_now(), "namespace": args.namespace,
             "analyses": analyses},
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
