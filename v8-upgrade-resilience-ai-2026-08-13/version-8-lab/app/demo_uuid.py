"""Feature 1 — string UUID to BinData, 7.x style vs 8.x $toUUID.

Both pipelines produce the same joined result: orders enriched with their
customer, keyed on a UUID. The difference is where the conversion happens and
how much of it you have to write.

  7.x style: MongoDB cannot convert a string to binData, so the application
             parses every UUID client-side and rewrites the query / documents.
  8.x style: $toUUID converts inside the server, so the pipeline is the whole
             conversion — no client-side parse step, and the same expression
             works in $project, $addFields, $lookup sub-pipelines, and $merge.
"""
import uuid

from bson.binary import Binary, UUID_SUBTYPE

from config import CUSTOMERS_COLLECTION, get_orders
from render import bindata_repr, header, pipeline_block, rows, section

_LIMIT = 3


def _seventies_pipeline() -> list:
    """Join on the raw string, then convert client-side after the fact."""
    return [
        {"$sort": {"order_date": 1}},
        {"$limit": _LIMIT},
        {"$lookup": {
            "from": CUSTOMERS_COLLECTION,
            "localField": "customer_id",
            "foreignField": "customer_id",
            "as": "customer",
        }},
        {"$unwind": "$customer"},
        {"$project": {
            "_id": 0,
            "order_id": 1,
            "customer_id": 1,
            "plan": "$customer.plan",
        }},
    ]


def _eighties_pipeline() -> list:
    """Convert in the server with $toUUID; the pipeline is the conversion."""
    return [
        {"$sort": {"order_date": 1}},
        {"$limit": _LIMIT},
        {"$lookup": {
            "from": CUSTOMERS_COLLECTION,
            "localField": "customer_id",
            "foreignField": "customer_id",
            "as": "customer",
        }},
        {"$unwind": "$customer"},
        {"$project": {
            "_id": 0,
            "order_id": {"$toUUID": "$order_id"},
            "customer_id": {"$toUUID": "$customer_id"},
            "plan": "$customer.plan",
        }},
    ]


def _convert_client_side(docs: list) -> list:
    """The code you delete when you move to 8.x."""
    converted = []
    for doc in docs:
        out = dict(doc)
        for field in ("order_id", "customer_id"):
            out[field] = Binary(uuid.UUID(doc[field]).bytes, UUID_SUBTYPE)
        converted.append(out)
    return converted


def _display(docs: list) -> list:
    return [
        {
            "order_id": bindata_repr(d["order_id"]),
            "customer_id": bindata_repr(d["customer_id"]),
            "plan": d["plan"],
        }
        for d in docs
    ]


def run() -> None:
    orders = get_orders()
    header("Feature 1 — $toUUID: string UUIDs to BinData subtype 4")

    before_raw = list(orders.aggregate(_seventies_pipeline()))
    before = _convert_client_side(before_raw)
    section("BEFORE (7.x style) — server returns strings, app converts")
    pipeline_block(_seventies_pipeline())
    print("  plus, for every document returned:")
    print('      Binary(uuid.UUID(doc["order_id"]).bytes, UUID_SUBTYPE)')
    print('      Binary(uuid.UUID(doc["customer_id"]).bytes, UUID_SUBTYPE)')
    rows(_display(before), ["order_id", "customer_id", "plan"])

    after = list(orders.aggregate(_eighties_pipeline()))
    section("AFTER (8.x) — $toUUID converts server-side")
    pipeline_block(_eighties_pipeline())
    rows(_display(after), ["order_id", "customer_id", "plan"])

    section("DIFF")
    identical = _display(before) == _display(after)
    print(f"  same result documents .............. {identical}")
    print("  client-side conversion code ........ "
          "2 lines per document -> 0")
    print("  round trips before you can filter/    "
          "\n    group/$merge on the UUID ......... 2 -> 1")
    print("  equivalent long form ............... "
          '{"$convert": {"input": "$order_id", '
          '"to": {"type": "binData", "subtype": 4}, "format": "uuid"}}')
