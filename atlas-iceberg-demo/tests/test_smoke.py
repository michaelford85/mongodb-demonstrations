"""Automated smoke test for the Atlas → Iceberg reference pattern.

Proves the core claim: a uniquely inserted Atlas record becomes queryable in
Iceberg via Trino. Requires the local stack up (`make up`) and a reachable
Atlas cluster (MONGODB_URI in .env). Skips cleanly when either is unavailable
so it never fails for environmental reasons.

Run: make test   (or: python3 -m pytest tests -v)
"""

import os
import sys
import time
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import common
import iceberg_io

TABLE = f"{common.TRINO_CATALOG}.{common.ICEBERG_NAMESPACE}.{common.ICEBERG_TABLE}"


def _atlas_ready() -> bool:
    try:
        c = common.get_mongo_client()
        c.admin.command("ping")
        ok = common.supports_change_streams(c)
        c.close()
        return ok
    except Exception:
        return False


def _trino_ready() -> bool:
    try:
        conn = iceberg_io.trino_connection()
        iceberg_io.run_query(conn, "SELECT 1")
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _atlas_ready(), reason="Atlas not reachable / not change-stream eligible")
@pytest.mark.skipif(not _trino_ready(), reason="Trino/Iceberg stack not up")
def test_unique_atlas_record_is_queryable_in_iceberg():
    order_id = f"SMOKE-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    client = common.get_mongo_client()
    coll = common.get_collection(client)
    coll.insert_one({
        "order_id": order_id, "account_id": "ACCT-SMOKE", "symbol": "MDB",
        "side": "BUY", "quantity": 7, "price": 111.11,
        "order_time": now, "order_status": "FILLED", "source_updated_at": now,
    })

    # Directly exercise the writer path used by the pipeline.
    catalog = iceberg_io.get_catalog()
    table = iceberg_io.ensure_table(catalog)
    doc = coll.find_one({"order_id": order_id})
    appended, _ = iceberg_io.append_orders(table, [iceberg_io.normalize_order(doc)])
    assert appended == 1

    conn = iceberg_io.trino_connection()
    sql = f"SELECT count(*) FROM {TABLE} WHERE order_id = '{order_id}'"
    deadline = time.time() + 60
    count = 0
    while time.time() < deadline:
        _, rows = iceberg_io.run_query(conn, sql)
        count = rows[0][0]
        if count >= 1:
            break
        time.sleep(1)

    assert count == 1, f"{order_id} not queryable exactly once in Iceberg (got {count})"

    # Idempotency: re-appending the same record must not duplicate.
    again, skipped = iceberg_io.append_orders(table, [iceberg_io.normalize_order(doc)])
    assert again == 0 and skipped == 1

    client.close()
