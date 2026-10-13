"""Seed, index, and reset the dedicated demo namespace.

Every destructive operation is guarded: it asserts the target database is the
demo database and only ever touches the three demo collections. Nothing here
runs automatically — the app calls it from an explicit, confirmed action, and
`seed_data.py` calls it from the command line.
"""

from __future__ import annotations

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database

from lib.mongo_client import (ACCOUNTS, COLLECTIONS, CUSTOMERS, DB_NAME,
                              TRANSACTIONS, get_db)
from lib.sample_data import (DEMO_TRANSFER_FLAG, TRANSFER_SOURCE,
                             TRANSFER_SOURCE_OPENING, TRANSFER_TARGET,
                             TRANSFER_TARGET_OPENING, build_all)
from lib.schema import apply_validators

# The only indexes this demo creates. Each one exists to serve a demonstrated
# access pattern — see the README table.
REQUIRED_INDEXES = {
    CUSTOMERS: {
        "preferences.contact_channel_1_address.state_1":
            ([("preferences.contact_channel", ASCENDING),
              ("address.state", ASCENDING)], {}),
    },
    ACCOUNTS: {
        "account_number_1": ([("account_number", ASCENDING)], {"unique": True}),
        "customer_id_1": ([("customer_id", ASCENDING)], {}),
    },
    TRANSACTIONS: {
        "account_number_1_posted_at_-1":
            ([("account_number", ASCENDING), ("posted_at", DESCENDING)], {}),
        "category_1_posted_at_-1":
            ([("category", ASCENDING), ("posted_at", DESCENDING)], {}),
    },
}


def _guard(db: Database) -> None:
    """Refuse to run a destructive operation outside the demo database."""
    if db.name != DB_NAME:
        raise RuntimeError(
            "Refusing to modify database '{}' — this demo only owns '{}'."
            .format(db.name, DB_NAME))


def create_indexes(db: Database = None) -> list:
    """Create the demo indexes. Idempotent. Returns the index names created."""
    db = get_db() if db is None else db
    _guard(db)
    created = []
    for coll, specs in REQUIRED_INDEXES.items():
        for name, (keys, opts) in specs.items():
            db[coll].create_index(keys, name=name, **opts)
            created.append("{}.{}".format(coll, name))
    return created


def missing_indexes(db: Database = None) -> list:
    """Names of required indexes that are not present."""
    db = get_db() if db is None else db
    missing = []
    for coll, specs in REQUIRED_INDEXES.items():
        try:
            present = set(db[coll].index_information().keys())
        except Exception:  # noqa: BLE001 — collection may not exist yet
            present = set()
        for name in specs:
            if name not in present:
                missing.append("{}.{}".format(coll, name))
    return missing


def seed(db: Database = None) -> dict:
    """Drop and rebuild the three demo collections from the deterministic seed.

    Each collection is recreated with its `$jsonSchema` validator before any
    document is inserted, so the seed itself is validated server-side.

    Returns a per-collection document count for display.
    """
    db = get_db() if db is None else db
    _guard(db)
    customer_docs, account_docs, txn_docs = build_all()

    for name in COLLECTIONS:
        db[name].drop()
    apply_validators(db)

    db[CUSTOMERS].insert_many(customer_docs)
    db[ACCOUNTS].insert_many(account_docs)
    db[TRANSACTIONS].insert_many(txn_docs)
    create_indexes(db)

    return {name: db[name].count_documents({}) for name in COLLECTIONS}


def reset_transaction_demo(db: Database = None) -> dict:
    """Undo only the transaction demo: restore balances, drop its writes.

    Cheaper than a full re-seed and enough to run the transaction section again.
    """
    db = get_db() if db is None else db
    _guard(db)
    for acct, opening in ((TRANSFER_SOURCE, TRANSFER_SOURCE_OPENING),
                          (TRANSFER_TARGET, TRANSFER_TARGET_OPENING)):
        db[ACCOUNTS].update_one({"account_number": acct},
                                {"$set": {"balance": opening}})
    removed = db[TRANSACTIONS].delete_many({DEMO_TRANSFER_FLAG: True})
    return {"balances_restored": 2, "demo_transfers_removed": removed.deleted_count}


def drop_demo_database() -> str:
    """Drop the entire demo database. Used by teardown.py only."""
    db = get_db()
    _guard(db)
    db.client.drop_database(DB_NAME)
    return DB_NAME
