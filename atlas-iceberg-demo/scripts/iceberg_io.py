"""Iceberg + Trino access for the demo.

The writer path uses PyIceberg (REST catalog + pyarrow S3 FileIO) to append
records directly to MinIO — no Spark writer is needed. Reads/SQL go through
Trino. Writes are idempotent: records whose ``order_id`` already exists in the
table are skipped, so a resume-token replay after a restart never duplicates.
"""

from datetime import datetime, timezone

import pyarrow as pa
import trino
from pyiceberg.catalog.rest import RestCatalog
from pyiceberg.exceptions import NamespaceAlreadyExistsError, NoSuchTableError
from pyiceberg.expressions import In
from pyiceberg.schema import Schema
from pyiceberg.types import DoubleType, LongType, NestedField, StringType, TimestamptzType

import common

ORDER_SCHEMA = Schema(
    NestedField(1, "order_id", StringType(), required=True),
    NestedField(2, "account_id", StringType(), required=False),
    NestedField(3, "symbol", StringType(), required=False),
    NestedField(4, "side", StringType(), required=False),
    NestedField(5, "quantity", LongType(), required=False),
    NestedField(6, "price", DoubleType(), required=False),
    NestedField(7, "order_time", TimestamptzType(), required=False),
    NestedField(8, "order_status", StringType(), required=False),
    NestedField(9, "source_updated_at", TimestamptzType(), required=False),
    NestedField(10, "iceberg_ingested_at", TimestamptzType(), required=False),
)

FIELD_ORDER = [f.name for f in ORDER_SCHEMA.fields]


def get_catalog() -> RestCatalog:
    return RestCatalog(
        "demo",
        **{
            "uri": common.ICEBERG_REST_URI,
            "warehouse": common.ICEBERG_WAREHOUSE,
            "s3.endpoint": common.S3_ENDPOINT,
            "s3.access-key-id": common.S3_ACCESS_KEY,
            "s3.secret-access-key": common.S3_SECRET_KEY,
            "s3.region": common.S3_REGION,
        },
    )


def ensure_table(catalog: RestCatalog):
    """Create the namespace/table on first use; return the loaded table."""
    try:
        catalog.create_namespace(common.ICEBERG_NAMESPACE)
    except NamespaceAlreadyExistsError:
        pass
    ident = (common.ICEBERG_NAMESPACE, common.ICEBERG_TABLE)
    try:
        return catalog.load_table(ident)
    except NoSuchTableError:
        return catalog.create_table(ident, schema=ORDER_SCHEMA)


def load_table_optional(catalog: RestCatalog):
    try:
        return catalog.load_table((common.ICEBERG_NAMESPACE, common.ICEBERG_TABLE))
    except NoSuchTableError:
        return None


def normalize_order(doc: dict) -> dict:
    """Map a MongoDB order document to the flat Iceberg record shape."""
    return {
        "order_id": str(doc["order_id"]),
        "account_id": doc.get("account_id"),
        "symbol": doc.get("symbol"),
        "side": doc.get("side"),
        "quantity": int(doc["quantity"]) if doc.get("quantity") is not None else None,
        "price": float(doc["price"]) if doc.get("price") is not None else None,
        "order_time": _as_utc(doc.get("order_time")),
        "order_status": doc.get("order_status"),
        "source_updated_at": _as_utc(doc.get("source_updated_at")),
        "iceberg_ingested_at": datetime.now(timezone.utc),
    }


def _as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def existing_order_ids(table, order_ids: list[str]) -> set[str]:
    if not order_ids:
        return set()
    scan = table.scan(row_filter=In("order_id", order_ids), selected_fields=("order_id",))
    return set(scan.to_arrow()["order_id"].to_pylist())


def append_orders(table, records: list[dict]) -> tuple[int, int]:
    """Append records, skipping any order_id already present. Returns
    (appended, skipped)."""
    if not records:
        return 0, 0
    present = existing_order_ids(table, [r["order_id"] for r in records])
    fresh = [r for r in records if r["order_id"] not in present]
    if not fresh:
        return 0, len(records)
    arrow_schema = table.schema().as_arrow()
    rows = [[r[name] for r in fresh] for name in FIELD_ORDER]
    pa_table = pa.Table.from_arrays(
        [pa.array(col) for col in rows], names=FIELD_ORDER
    ).cast(arrow_schema)
    table.append(pa_table)
    return len(fresh), len(records) - len(fresh)


# ── Trino SQL ──────────────────────────────────────────────────────────────────
def trino_connection():
    return trino.dbapi.connect(
        host=common.TRINO_HOST,
        port=common.TRINO_PORT,
        user=common.TRINO_USER,
        catalog=common.TRINO_CATALOG,
        schema=common.ICEBERG_NAMESPACE,
    )


def run_query(conn, sql: str):
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description] if cur.description else []
    return cols, rows
