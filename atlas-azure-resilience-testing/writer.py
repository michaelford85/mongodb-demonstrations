"""Monotonic majority writer — the write-availability probe for every test case.

Inserts one sequentially-numbered document per interval with w="majority" and
retryable writes enabled. Because `_id` is the sequence number, a duplicate-key
error proves a write was acknowledged that the client believed had failed, and a
missing number proves a lost write. On exit the script re-reads the collection
and reports the longest interval with no successful acknowledgement — the
observed write-unavailability window for that run.

    python3 writer.py --label t3-failover-idle

Artefacts: results/writer-<label>-<timestamp>.jsonl (one record per attempt)
and a summary printed to stdout.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time

from pymongo import MongoClient, WriteConcern
from pymongo.errors import DuplicateKeyError, PyMongoError

from common import (append_jsonl, artefact_path, load_env, require_env,
                    utc_now)

COLLECTION = "write_probe"


def summarise(coll, attempts: int, acked: int, gaps: list[dict]) -> None:
    observed = coll.count_documents({})
    highest = coll.find_one(sort=[("_id", -1)]) or {}
    missing = (highest.get("_id", 0)) - observed

    print("\n--- writer summary ---")
    print(f"  attempts                 : {attempts}")
    print(f"  acknowledged             : {acked}")
    print(f"  documents present        : {observed}")
    print(f"  highest sequence number  : {highest.get('_id', 0)}")
    print(f"  missing sequence numbers : {missing}")
    if gaps:
        worst = max(gaps, key=lambda g: g["seconds"])
        print(f"  longest ack gap          : {worst['seconds']:.1f} s "
              f"(from #{worst['fromSeq']} at {worst['fromTs']})")
        print(f"  gaps over threshold      : {len(gaps)}")
    else:
        print("  longest ack gap          : none over threshold")
    print("----------------------\n")


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Monotonic majority writer")
    parser.add_argument("--label", required=True,
                        help="Test case label, used in the artefact filename")
    parser.add_argument("--gap-threshold", type=float, default=1.0,
                        help="Record an ack gap longer than this many seconds")
    args = parser.parse_args()

    uri = require_env("TEST_CLUSTER_URI")
    db_name = os.getenv("TEST_DB", "resilience_test")
    interval = float(os.getenv("WRITER_INTERVAL", "0.2"))

    client = MongoClient(uri, retryWrites=True, w="majority")
    coll = client[db_name].get_collection(
        COLLECTION, write_concern=WriteConcern("majority")
    )

    log = artefact_path(f"writer-{args.label}", "jsonl")
    print(f"Writer -> {db_name}.{COLLECTION}  (interval {interval}s, "
          f"w=majority, retryWrites=true)")
    print(f"Log    -> {log}")
    print("Stop with Ctrl+C once the test case is complete.\n")

    # Start from the current high-water mark so reruns extend the same sequence.
    last = coll.find_one(sort=[("_id", -1)]) or {}
    seq = int(last.get("_id", 0))

    attempts = 0
    acked = 0
    gaps: list[dict] = []
    last_ack = time.monotonic()
    last_ack_seq = seq
    last_ack_ts = utc_now()

    def handle_sigint(_sig, _frame):
        summarise(coll, attempts, acked, gaps)
        client.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    while True:
        seq += 1
        attempts += 1
        started = time.monotonic()
        record = {"ts": utc_now(), "seq": seq}
        try:
            coll.insert_one({"_id": seq, "ts": utc_now(), "payload": "x" * 256})
            elapsed_ms = (time.monotonic() - started) * 1000
            acked += 1
            record.update({"result": "ack", "latencyMs": round(elapsed_ms, 1)})

            since_ack = started - last_ack
            if since_ack > args.gap_threshold:
                gap = {
                    "seconds": round(since_ack, 2),
                    "fromSeq": last_ack_seq,
                    "fromTs": last_ack_ts,
                    "toSeq": seq,
                }
                gaps.append(gap)
                print(f"  GAP    {gap['seconds']:.1f}s with no acknowledged write "
                      f"(#{last_ack_seq} -> #{seq})")
            last_ack = time.monotonic()
            last_ack_seq = seq
            last_ack_ts = record["ts"]
            print(f"  #{seq:>7}  ack in {elapsed_ms:7.1f} ms")
        except DuplicateKeyError:
            # A previous attempt was durable even though the client saw an error.
            record.update({"result": "duplicate"})
            print(f"  #{seq:>7}  DUPLICATE — earlier attempt was durable")
        except PyMongoError as exc:
            elapsed_ms = (time.monotonic() - started) * 1000
            record.update({
                "result": "error",
                "latencyMs": round(elapsed_ms, 1),
                "error": type(exc).__name__,
            })
            print(f"  #{seq:>7}  FAILED after {elapsed_ms:7.1f} ms: "
                  f"{type(exc).__name__}")

        append_jsonl(log, record)
        time.sleep(interval)


if __name__ == "__main__":
    main()
