"""
Exports the operational collections from Atlas to S3 as JSONL.

This is the handoff boundary between Atlas (operational) and Databricks
(analytics). In a real deployment the same pattern is implemented by one
of three production-grade options:

  1. Atlas Data Federation $out to S3 — server-side, no app code
  2. A scheduled job using mongoexport, AWS DMS, or a stream consumer
     of Atlas change streams
  3. The MongoDB Spark Connector reading directly from Atlas into Databricks
     (no S3 in the path) — preferred when the analytics platform can pull
     rather than be pushed to

This script implements option 2 in its simplest form: a one-shot full
export per collection. It is intentionally small so an SA can show the
shape of the handoff in a meeting and then describe the production
options above.

If AWS_S3_BUCKET is set in .env the export uses boto3 to upload directly
to S3. If it is blank the export writes to ./_s3_export/ locally and is
clearly labelled as a stand-in. The downstream analytics_simulation.py
reads from whichever location was used.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGODB_URI    = os.environ["MONGODB_URI"]
DB_NAME        = os.environ.get("DB_NAME", "atlas_databricks_demo")
AWS_REGION     = os.environ.get("AWS_REGION", "us-east-1")
AWS_S3_BUCKET  = os.environ.get("AWS_S3_BUCKET", "").strip()
AWS_S3_PREFIX  = os.environ.get("AWS_S3_PREFIX", "atlas-exports/").rstrip("/") + "/"

COLLECTIONS = ["customers", "products", "orders", "events"]
LOCAL_DIR   = Path(__file__).parent / "_s3_export"


def encode(doc) -> str:
    """JSONL-safe encoder: ObjectId → str, datetime → ISO 8601."""
    def default(o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.astimezone(timezone.utc).isoformat()
        raise TypeError(f"Unserialisable type: {type(o)}")
    return json.dumps(doc, default=default)


def dump_collection_to_jsonl(db, name: str, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w") as f:
        for doc in db[name].find():
            f.write(encode(doc) + "\n")
            count += 1
    return count


def upload_to_s3(local_path: Path, bucket: str, key: str) -> None:
    import boto3  # imported lazily so the demo runs without AWS deps installed
    s3 = boto3.client("s3", region_name=AWS_REGION)
    s3.upload_file(str(local_path), bucket, key)


def main():
    print(f"=== Export Atlas → S3 (analytics handoff)  |  {DB_NAME} ===")
    using_real_s3 = bool(AWS_S3_BUCKET)
    if using_real_s3:
        print(f"  Target  : s3://{AWS_S3_BUCKET}/{AWS_S3_PREFIX}")
        print(f"  Region  : {AWS_REGION}")
        # boto3 imported here only so the message above appears even if creds
        # are missing — gives a cleaner error path.
        try:
            import boto3  # noqa: F401
        except ImportError:
            raise SystemExit("AWS_S3_BUCKET is set but boto3 is not installed. "
                             "pip install -r requirements.txt")
    else:
        print(f"  Target  : {LOCAL_DIR}  (local stand-in for S3 — set AWS_S3_BUCKET")
        print(f"            in .env to upload to a real bucket instead)")

    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)
    db = client[DB_NAME]

    # All exports for one logical batch share a timestamp prefix — this mirrors
    # how Databricks Auto Loader / Delta partitions ingested data by export run.
    batch = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(f"  Batch   : {batch}")
    print()

    totals = {}
    for coll in COLLECTIONS:
        local_path = LOCAL_DIR / batch / f"{coll}.jsonl"
        count = dump_collection_to_jsonl(db, coll, local_path)
        totals[coll] = count
        if using_real_s3:
            key = f"{AWS_S3_PREFIX}{batch}/{coll}.jsonl"
            upload_to_s3(local_path, AWS_S3_BUCKET, key)
            print(f"  {coll:<10} {count:>6} docs  →  s3://{AWS_S3_BUCKET}/{key}")
        else:
            print(f"  {coll:<10} {count:>6} docs  →  {local_path.relative_to(Path.cwd()) if local_path.is_relative_to(Path.cwd()) else local_path}")

    # A tiny manifest makes the downstream reader's job easy and mirrors the
    # _manifest.json files real ETL pipelines emit per batch.
    manifest = {"batch": batch, "database": DB_NAME, "collections": totals}
    manifest_path = LOCAL_DIR / batch / "_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    if using_real_s3:
        upload_to_s3(manifest_path, AWS_S3_BUCKET, f"{AWS_S3_PREFIX}{batch}/_manifest.json")

    client.close()
    print()
    print("Export complete. This is the operational/analytics boundary.")
    print("Everything downstream of here belongs to the lakehouse:")
    print("  python3 analytics_simulation.py   — runs the Databricks-shaped workload")
    print("  cat notebook_equivalent.py        — shows the PySpark this maps to")


if __name__ == "__main__":
    main()
