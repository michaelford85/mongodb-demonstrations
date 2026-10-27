"""Shared, testable transformation of AWS DMS Kafka messages.

The ASP pipeline in stream-processing/asp_pipeline.json implements the same
logic declaratively. This module mirrors it so unit tests can prove the
transform with synthetic fixtures, without AWS, Atlas, or API credentials.

DMS Kafka message shape (MessageFormat=json, IncludeTransactionDetails=true):
{
  "data": {"id": 1, "title": "...", ...},        # full row for load/insert/update,
                                                  # PK (or full row with REPLICA IDENTITY
                                                  # FULL) for delete
  "metadata": {
    "record-type": "data",                       # or "control"
    "operation": "load" | "insert" | "update" | "delete",
    "schema-name": "demo_schema",
    "table-name": "knowledge_items",
    "timestamp": "2026-10-22T00:00:00.000000Z"
  }
}
"""

from __future__ import annotations

TABLE_NAME = "knowledge_items"
OPERATIONS = ("load", "insert", "update", "delete")


def transform(message: dict) -> dict | None:
    """Map a DMS Kafka message to the Atlas read-model document.

    Returns None for control records, non-CDC tables, unknown operations,
    and malformed messages (the ASP pipeline sends erroring messages to the
    DLQ; here callers decide). Replayed/duplicate events are idempotent:
    the read model is keyed by the PostgreSQL primary key, so applying the
    same event twice yields the same document.
    """
    if not isinstance(message, dict):
        return None

    metadata = message.get("metadata") or {}
    data = message.get("data")

    if metadata.get("record-type", "data") != "data":
        return None
    if metadata.get("table-name") != TABLE_NAME:
        return None
    if metadata.get("operation") not in OPERATIONS:
        return None
    if not isinstance(data, dict) or data.get("id") is None:
        return None

    is_delete = metadata["operation"] == "delete"

    # A delete event must still identify the row. Everything else needs
    # the fields we embed.
    if not str(data["id"]).strip():
        return None
    if not is_delete and not (data.get("title") or data.get("body")):
        return None

    searchable = " ".join(
        str(data.get(f, "") or "")
        for f in ("title", "body", "tags", "entity_type", "department")
    )

    return {
        "_id": f"knowledge-items-{data['id']}",
        "entity_type": data.get("entity_type", ""),
        "source_id": str(data["id"]),
        "title": data.get("title", ""),
        "body": data.get("body", ""),
        "tags": data.get("tags", ""),
        "department": data.get("department", ""),
        "author": data.get("author", ""),
        "is_active": data.get("is_active", False),
        "searchable_text": " ".join(searchable.split()),
        "source_updated_at": data.get("updated_at"),
        "cdc_operation": metadata["operation"],
        "cdc_ts": metadata.get("timestamp"),
        "_is_delete": is_delete,
    }
