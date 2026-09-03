"""Demonstrate restart safety: restarting the pipeline creates no duplicates.

Steps:
  1. Record the current Iceberg row count.
  2. Insert a fresh live order into Atlas.
  3. Run the pipeline briefly so it processes and checkpoints the order.
  4. Restart the pipeline (still resuming from the same checkpoint) and let it
     re-observe recent events.
  5. Assert the order appears exactly once and the row count grew by exactly 1.

Idempotency comes from two layers (see pipeline.py): the durable resume token
and dedup-on-write by order_id.
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import iceberg_io

log = common.get_logger("verify-restart")

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
TABLE = f"{common.TRINO_CATALOG}.{common.ICEBERG_NAMESPACE}.{common.ICEBERG_TABLE}"


def count_rows(conn) -> int:
    _, rows = iceberg_io.run_query(conn, f"SELECT count(*) FROM {TABLE}")
    return rows[0][0]


def count_order(conn, order_id: str) -> int:
    _, rows = iceberg_io.run_query(
        conn, f"SELECT count(*) FROM {TABLE} WHERE order_id = '{order_id}'")
    return rows[0][0]


def run_pipeline_once(seconds: int) -> None:
    subprocess.run([PY, os.path.join(SCRIPTS, "pipeline.py"),
                    "--max-seconds", str(seconds)], check=True)


def main() -> None:
    common.banner("VERIFY RESTART · idempotency / no duplicates")
    conn = iceberg_io.trino_connection()

    before = count_rows(conn)
    order_id = f"LIVE-RESTART-{int(time.time() * 1000)}"
    log.info("Rows before          : %d", before)

    subprocess.run([PY, os.path.join(SCRIPTS, "live_order.py"),
                    "--order-id", order_id], check=True)

    log.info("Pipeline run #1 (initial capture)...")
    run_pipeline_once(6)
    after_first = count_order(conn, order_id)

    log.info("Pipeline run #2 (restart from checkpoint — should NOT duplicate)...")
    run_pipeline_once(6)
    after_second = count_order(conn, order_id)
    total = count_rows(conn)

    log.info("Occurrences of %s after run #1: %d", order_id, after_first)
    log.info("Occurrences of %s after run #2: %d", order_id, after_second)
    log.info("Rows after           : %d (delta %+d)", total, total - before)

    if after_second == 1 and (total - before) == 1:
        log.info("PASS restart is safe — exactly one copy of the live order.")
    else:
        log.error("FAIL duplication detected on restart.")
        sys.exit(1)


if __name__ == "__main__":
    main()
