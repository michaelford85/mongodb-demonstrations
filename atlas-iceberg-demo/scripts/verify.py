"""Verify end-to-end visibility and report latency.

Reads the live order recorded by live_order.py, polls the Iceberg table via
Trino (bounded timeout) until the row appears, then prints the Iceberg
visibility timestamp and the measured Atlas → Iceberg latency.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import iceberg_io

log = common.get_logger("verify")

LIVE_ORDER_FILE = common.STATE_DIR / "live_order.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify live order visibility in Iceberg")
    parser.add_argument("--order-id", default=None)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    common.banner("VERIFY · Atlas → Iceberg visibility latency")

    order_id, atlas_insert_at = args.order_id, None
    if LIVE_ORDER_FILE.exists():
        saved = json.loads(LIVE_ORDER_FILE.read_text())
        order_id = order_id or saved.get("order_id")
        atlas_insert_at = saved.get("atlas_insert_at")
    if not order_id:
        log.error("No order id — run `make demo` or pass --order-id.")
        sys.exit(1)

    conn = iceberg_io.trino_connection()
    sql = ("SELECT iceberg_ingested_at, source_updated_at "
           f"FROM {common.TRINO_CATALOG}.{common.ICEBERG_NAMESPACE}.{common.ICEBERG_TABLE} "
           f"WHERE order_id = '{order_id}'")

    log.info("Waiting for %s to appear in Iceberg (timeout %ds)...", order_id, args.timeout)
    deadline = time.time() + args.timeout
    row = None
    while time.time() < deadline:
        _, rows = iceberg_io.run_query(conn, sql)
        if rows:
            row = rows[0]
            break
        time.sleep(1)

    if not row:
        log.error("FAIL %s not visible within %ds.", order_id, args.timeout)
        sys.exit(1)

    ingested_at, source_updated_at = row[0], row[1]
    log.info("Live order id        : %s", order_id)
    if atlas_insert_at:
        log.info("Atlas insert time    : %s", atlas_insert_at)
    log.info("Iceberg visible time : %s", ingested_at.isoformat())

    baseline = _parse(atlas_insert_at) if atlas_insert_at else source_updated_at
    if baseline is not None:
        latency = (ingested_at - baseline).total_seconds()
        log.info("End-to-end latency   : %.2f seconds", latency)


def _parse(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


if __name__ == "__main__":
    main()
