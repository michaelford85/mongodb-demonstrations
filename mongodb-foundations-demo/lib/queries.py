"""Prebuilt, bounded query / aggregation / explain examples.

Nothing here accepts free-form input: the pages pass values chosen from the
allowlists defined in `lib.sample_data`, so a demo can never run an arbitrary
query. Every read carries a max-time budget.
"""

from __future__ import annotations

from datetime import timedelta

from bson import json_util

from lib.mongo_client import (ACCOUNTS, CUSTOMERS, QUERY_TIMEOUT_MS,
                              TRANSACTIONS, get_db)
from lib.sample_data import BASE_DATE

CUSTOMER_PROJECTION = {
    "_id": 0, "customer_id": 1, "name.first": 1, "name.last": 1,
    "address.city": 1, "address.state": 1,
    "preferences.contact_channel": 1, "preferences.paperless": 1,
}


def as_mql(obj) -> str:
    """Render a filter or pipeline as readable extended-JSON MQL."""
    return json_util.dumps(obj, indent=2)


def customer_filter(channel: str, state: str) -> dict:
    """Filter on a nested preference and nested geography field."""
    return {"preferences.contact_channel": channel, "address.state": state}


def run_customer_filter(channel: str, state: str) -> list:
    """Example 1: find + project. Returns flattened rows for a table."""
    cursor = (get_db()[CUSTOMERS]
              .find(customer_filter(channel, state), CUSTOMER_PROJECTION)
              .sort("customer_id", 1)
              .max_time_ms(QUERY_TIMEOUT_MS))
    rows = []
    for doc in cursor:
        rows.append({
            "customer_id": doc["customer_id"],
            "first_name": doc["name"]["first"],
            "last_name": doc["name"]["last"],
            "city": doc["address"]["city"],
            "state": doc["address"]["state"],
            "contact_channel": doc["preferences"]["contact_channel"],
            "paperless": doc["preferences"]["paperless"],
        })
    return rows


def spend_by_category_pipeline(days: int) -> list:
    """$match + $group: spend per category over a recent window."""
    since = BASE_DATE - timedelta(days=days)
    return [
        {"$match": {"direction": "debit", "posted_at": {"$gte": since}}},
        {"$group": {"_id": "$category",
                    "transactions": {"$sum": 1},
                    "total_amount": {"$sum": "$amount"},
                    "average_amount": {"$avg": "$amount"}}},
        {"$sort": {"total_amount": -1}},
    ]


def spend_by_customer_pipeline(days: int, limit: int = 10) -> list:
    """$match + $group + $sort + $limit: top spenders over a recent window."""
    since = BASE_DATE - timedelta(days=days)
    return [
        {"$match": {"direction": "debit", "posted_at": {"$gte": since}}},
        {"$group": {"_id": "$customer_id",
                    "transactions": {"$sum": 1},
                    "total_amount": {"$sum": "$amount"}}},
        {"$sort": {"total_amount": -1}},
        {"$limit": limit},
    ]


def run_pipeline(pipeline: list, group_label: str) -> list:
    """Execute an aggregation and return rounded, table-ready rows."""
    rows = []
    for doc in get_db()[TRANSACTIONS].aggregate(
            pipeline, maxTimeMS=QUERY_TIMEOUT_MS):
        row = {group_label: doc["_id"], "transactions": doc["transactions"],
               "total_amount": round(doc["total_amount"], 2)}
        if "average_amount" in doc:
            row["average_amount"] = round(doc["average_amount"], 2)
        rows.append(row)
    return rows


def indexed_accounts() -> list:
    """Account numbers that carry seeded transaction history, for the picker."""
    return sorted(get_db()[TRANSACTIONS].distinct("account_number"))


def statement_filter(account_number: str, days: int) -> dict:
    """The query the compound index (account_number, posted_at) serves."""
    return {"account_number": account_number,
            "posted_at": {"$gte": BASE_DATE - timedelta(days=days)}}


def run_statement(account_number: str, days: int, limit: int = 25) -> list:
    cursor = (get_db()[TRANSACTIONS]
              .find(statement_filter(account_number, days),
                    {"_id": 0, "txn_id": 1, "posted_at": 1, "category": 1,
                     "merchant": 1, "direction": 1, "amount": 1})
              .sort("posted_at", -1).limit(limit)
              .max_time_ms(QUERY_TIMEOUT_MS))
    return list(cursor)


def index_list(collection: str) -> list:
    """Presenter-friendly index inventory for one demo collection."""
    info = get_db()[collection].index_information()
    rows = []
    for name, spec in sorted(info.items()):
        rows.append({
            "index": name,
            "keys": ", ".join("{}: {}".format(f, d) for f, d in spec["key"]),
            "unique": bool(spec.get("unique", False)),
        })
    return rows


def index_inventory() -> dict:
    return {name: index_list(name)
            for name in (CUSTOMERS, ACCOUNTS, TRANSACTIONS)}


def _walk_plan(plan: dict, stages: list, indexes: list) -> None:
    """Collect stage names and index names from a winning-plan tree."""
    if not isinstance(plan, dict):
        return
    if "stage" in plan:
        stages.append(plan["stage"])
    if "indexName" in plan:
        indexes.append(plan["indexName"])
    for key in ("inputStage", "queryPlan"):
        if key in plan:
            _walk_plan(plan[key], stages, indexes)
    for child in plan.get("inputStages", []) or []:
        _walk_plan(child, stages, indexes)


def explain_statement(account_number: str, days: int, limit: int = 25,
                      force_collection_scan: bool = False) -> dict:
    """Run `explain` in executionStats mode and return presenter-safe fields.

    With `force_collection_scan`, the query is hinted to $natural so the same
    query can be compared against a scan without dropping any index.
    """
    find_cmd = {
        "find": TRANSACTIONS,
        "filter": statement_filter(account_number, days),
        "sort": {"posted_at": -1},
        "limit": limit,
        "maxTimeMS": QUERY_TIMEOUT_MS,
    }
    if force_collection_scan:
        find_cmd["hint"] = {"$natural": 1}

    raw = get_db().command({"explain": find_cmd,
                            "verbosity": "executionStats"})
    planner = raw.get("queryPlanner", {})
    stats = raw.get("executionStats", {})
    stages, indexes = [], []
    _walk_plan(planner.get("winningPlan", {}), stages, indexes)

    return {
        "plan": " → ".join(stages) if stages else "not reported",
        "index_used": indexes[0] if indexes else "none (collection scan)",
        "keys_examined": stats.get("totalKeysExamined"),
        "documents_examined": stats.get("totalDocsExamined"),
        "documents_returned": stats.get("nReturned"),
        "execution_time_ms": stats.get("executionTimeMillis"),
        "command": find_cmd,
    }
