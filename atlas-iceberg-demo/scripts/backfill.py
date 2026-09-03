"""Backfill the historical Atlas orders into the Iceberg table.

Creates the Iceberg namespace/table on first run, then appends every order
currently in the source collection. Idempotent: rerunning skips order_ids that
are already present, so it is safe to run repeatedly.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import iceberg_io

log = common.get_logger("backfill")

BATCH = 200


def main() -> None:
    common.banner("BACKFILL · Atlas history → Iceberg")

    catalog = iceberg_io.get_catalog()
    table = iceberg_io.ensure_table(catalog)
    log.info("Iceberg table ready: %s.%s", common.ICEBERG_NAMESPACE, common.ICEBERG_TABLE)

    client = common.get_mongo_client()
    try:
        coll = common.get_collection(client)
        total = coll.count_documents({})
        log.info("Reading %d source orders from %s.%s", total,
                 common.DB_NAME, common.COLLECTION_NAME)

        appended = skipped = 0
        buffer: list[dict] = []
        for doc in coll.find({}, sort=[("order_time", 1)]):
            buffer.append(iceberg_io.normalize_order(doc))
            if len(buffer) >= BATCH:
                a, s = iceberg_io.append_orders(table, buffer)
                appended += a
                skipped += s
                buffer = []
        if buffer:
            a, s = iceberg_io.append_orders(table, buffer)
            appended += a
            skipped += s

        log.info("Backfill complete: %d appended, %d already present", appended, skipped)
        log.info("Next: make start   (then, in the demo, insert a live order)")
    finally:
        client.close()


if __name__ == "__main__":
    main()
