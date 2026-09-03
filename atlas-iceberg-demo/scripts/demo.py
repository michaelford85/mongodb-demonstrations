"""Orchestrate the live portion of the demonstration.

Assumes infra is up and history has been backfilled (`make up check seed
backfill`). This script:
  1. starts the Change Streams pipeline as a background process,
  2. inserts one memorable live order into Atlas,
  3. verifies it becomes visible in Iceberg and prints end-to-end latency,
  4. stops the pipeline.

Run `make query` afterwards for the analytical SQL, and `make verify-restart`
to demonstrate restart safety (no duplicates).
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

log = common.get_logger("demo")

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def main() -> None:
    common.banner("DEMO · live order → Change Streams → Iceberg")

    order_id = f"LIVE-{int(time.time() * 1000)}"
    log.info("Starting Change Streams pipeline (background)...")
    pipe = subprocess.Popen([PY, os.path.join(SCRIPTS, "pipeline.py")])
    try:
        time.sleep(3)  # let the stream open before the live insert
        subprocess.run([PY, os.path.join(SCRIPTS, "live_order.py"),
                        "--order-id", order_id], check=True)
        subprocess.run([PY, os.path.join(SCRIPTS, "verify.py"),
                        "--order-id", order_id, "--timeout", "90"], check=True)
    finally:
        log.info("Stopping pipeline...")
        pipe.terminate()
        try:
            pipe.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pipe.kill()

    common.banner("DEMO complete")
    log.info("Live order id: %s", order_id)
    log.info("Next: make query          (analytical SQL over Iceberg)")
    log.info("      make verify-restart  (prove restart safety / no duplicates)")


if __name__ == "__main__":
    main()
