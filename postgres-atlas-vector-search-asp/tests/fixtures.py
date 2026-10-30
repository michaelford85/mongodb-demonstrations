"""Synthetic AWS DMS Kafka message fixtures — no AWS/Atlas/API access needed."""

from __future__ import annotations

import json
from pathlib import Path


def dms_message(
    row_id: int,
    operation: str = "insert",
    title: str = "Resetting your workspace password",
    body: str = "Step-by-step process with expected turnaround time.",
    tags: str = "howto,it",
    entity_type: str = "article",
    department: str = "it",
    **overrides,
) -> dict:
    data = {
        "id": row_id,
        "entity_type": entity_type,
        "title": title,
        "body": body,
        "tags": tags,
        "department": department,
        "author": "demo-author",
        "is_active": True,
        "updated_at": "2026-10-22 10:00:00+00",
    }
    if operation == "delete":
        data = {"id": row_id}
    data.update(overrides)
    return {
        "data": data,
        "metadata": {
            "timestamp": "2026-10-22T10:00:01.123456Z",
            "record-type": "data",
            "operation": operation,
            "partition-key-type": "primary-key",
            "partition-key-value": f"demo_schema.knowledge_items.{row_id}",
            "schema-name": "demo_schema",
            "table-name": "knowledge_items",
        },
    }


def control_message() -> dict:
    return {
        "control": {"table-def": {"columns": {}}},
        "metadata": {
            "timestamp": "2026-10-22T10:00:00.000000Z",
            "record-type": "control",
            "operation": "create-table",
            "schema-name": "demo_schema",
            "table-name": "knowledge_items",
        },
    }


def sample_messages() -> list[dict]:
    """A realistic stream: snapshot load, insert, update, delete, control record."""
    return [
        control_message(),
        dms_message(1, "load"),
        dms_message(2, "insert", title="Quarterly reporting cycles", entity_type="faq"),
        dms_message(3, "update", body="Revised walkthrough for the new release."),
        dms_message(2, "delete"),
    ]


def load_pipeline_json() -> dict:
    path = Path(__file__).parent.parent / "stream-processing" / "asp_pipeline.json"
    return json.loads(path.read_text())
