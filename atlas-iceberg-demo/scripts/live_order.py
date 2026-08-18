"""Insert one memorable "live" securities order into Atlas.

Prints the Atlas insert timestamp so the demo can later compute end-to-end
visibility latency once the record surfaces in Iceberg. The order_id is unique
per run (LIVE-<epoch-ms>) unless one is supplied with --order-id.
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

log = common.get_logger("live-order")

LIVE_ORDER_FILE = common.STATE_DIR / "live_order.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Insert one live order into Atlas")
    parser.add_argument("--order-id", default=f"LIVE-{int(time.time() * 1000)}")
    parser.add_argument("--symbol", default="MDB")
    parser.add_argument("--quantity", type=int, default=1_000)
    args = parser.parse_args()

    common.banner("LIVE ORDER · insert into Atlas")
    client = common.get_mongo_client()
    try:
        coll = common.get_collection(client)
        now = datetime.now(timezone.utc)
        order = {
            "order_id": args.order_id,
            "account_id": "ACCT-9001",
            "symbol": args.symbol,
            "side": random.choice(["BUY", "SELL"]),
            "quantity": args.quantity,
            "price": 357.42,
            "order_time": now,
            "order_status": "FILLED",
            "source_updated_at": now,
        }
        coll.insert_one(order)

        common.STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(LIVE_ORDER_FILE, "w") as f:
            json.dump({"order_id": args.order_id,
                       "atlas_insert_at": now.isoformat()}, f)

        log.info("Inserted live order  : %s", args.order_id)
        log.info("Atlas insert time    : %s", now.isoformat())
        log.info("Now watch it surface in Iceberg: make verify")
    finally:
        client.close()


if __name__ == "__main__":
    main()
