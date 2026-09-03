"""Continuous Change Streams → Iceberg pipeline.

Consumes insert/replace/update events from the Atlas source collection with
``full_document='updateLookup'`` and appends normalized records to Iceberg.

Restart safety / idempotency (two independent guarantees):
  1. Durable resume token — the change-stream ``_id`` is written to
     state/resume_token.json (atomically) after every processed event, so a
     restart resumes exactly where it left off, within Atlas's oplog window.
  2. Dedup-on-write — append_orders() skips any order_id already in the table,
     so even an at-least-once replay after an unclean stop never duplicates.

Deletes are logged as tombstones. This append-only demo does not remove rows;
the README documents how a delete would be represented in Iceberg.
"""

import argparse
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import iceberg_io

log = common.get_logger("pipeline")

_running = True


def _stop(signum, _frame):
    global _running
    _running = False
    log.info("Signal %s received — shutting down gracefully.", signum)


def process_event(table, event) -> bool:
    """Return True if a record was written to Iceberg."""
    op = event["operationType"]
    if op == "delete":
        key = event.get("documentKey", {}).get("_id")
        log.info("Tombstone (delete) for %s — not applied in append-only demo.", key)
        return False
    doc = event.get("fullDocument")
    if not doc:
        return False
    appended, _ = iceberg_io.append_orders(table, [iceberg_io.normalize_order(doc)])
    if appended:
        log.info("Streamed order %s (%s %s x%s) → Iceberg",
                 doc.get("order_id"), doc.get("side"),
                 doc.get("symbol"), doc.get("quantity"))
    return bool(appended)


def main() -> None:
    parser = argparse.ArgumentParser(description="Atlas Change Streams → Iceberg pipeline")
    parser.add_argument("--max-events", type=int, default=0, help="stop after N events (0 = run forever)")
    parser.add_argument("--max-seconds", type=int, default=0, help="stop after S seconds (0 = run forever)")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    common.banner("PIPELINE · Atlas Change Streams → Iceberg")
    catalog = iceberg_io.get_catalog()
    table = iceberg_io.ensure_table(catalog)

    client = common.get_mongo_client()
    coll = common.get_collection(client)

    resume = common.load_resume_token()
    kwargs = {"full_document": "updateLookup"}
    if resume:
        kwargs["resume_after"] = resume
        log.info("Resuming from saved checkpoint (no duplicates on restart).")
    else:
        log.info("No checkpoint found — watching for new changes from now.")

    pipeline = [{"$match": {"operationType": {"$in": ["insert", "replace", "update", "delete"]}}}]
    written = 0
    start = time.time()
    try:
        with coll.watch(pipeline, **kwargs) as stream:
            log.info("Watching %s.%s — Ctrl+C to stop.", common.DB_NAME, common.COLLECTION_NAME)
            while _running:
                event = stream.try_next()
                if event is None:
                    if args.max_seconds and (time.time() - start) >= args.max_seconds:
                        break
                    time.sleep(0.25)
                    continue
                if process_event(table, event):
                    written += 1
                common.save_resume_token(event["_id"])  # checkpoint every event
                if args.max_events and written >= args.max_events:
                    break
    finally:
        client.close()
        log.info("Pipeline stopped. %d record(s) written this run.", written)


if __name__ == "__main__":
    main()
