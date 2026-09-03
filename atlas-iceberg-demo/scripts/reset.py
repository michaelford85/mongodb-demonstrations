"""Reset demo data safely and idempotently.

Removes ONLY resources this demo created:
  - the Iceberg table and namespace (via the REST catalog),
  - objects under the MinIO warehouse bucket,
  - the Atlas demo database (DB_NAME only — no other namespace is touched),
  - local checkpoint/state files.

Infrastructure containers keep running; use `make down` to stop them. Every
step is best-effort so reset can be run repeatedly without error.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import boto3
from botocore.client import Config

import common
import iceberg_io

log = common.get_logger("reset")


def drop_iceberg() -> None:
    try:
        catalog = iceberg_io.get_catalog()
    except Exception as e:
        log.warning("Skip Iceberg drop (catalog unreachable): %s", type(e).__name__)
        return
    ident = (common.ICEBERG_NAMESPACE, common.ICEBERG_TABLE)
    try:
        catalog.drop_table(ident)
        log.info("Dropped Iceberg table %s.%s", *ident)
    except Exception:
        log.info("Iceberg table already absent")
    try:
        catalog.drop_namespace(common.ICEBERG_NAMESPACE)
        log.info("Dropped Iceberg namespace %s", common.ICEBERG_NAMESPACE)
    except Exception:
        log.info("Iceberg namespace already absent")


def empty_bucket() -> None:
    try:
        s3 = boto3.resource(
            "s3", endpoint_url=common.S3_ENDPOINT,
            aws_access_key_id=common.S3_ACCESS_KEY,
            aws_secret_access_key=common.S3_SECRET_KEY,
            region_name=common.S3_REGION,
            config=Config(s3={"addressing_style": "path"}),
        )
        bucket = s3.Bucket(common.S3_BUCKET)
        bucket.objects.all().delete()
        log.info("Emptied MinIO bucket %s", common.S3_BUCKET)
    except Exception as e:
        log.warning("Skip bucket empty (MinIO unreachable): %s", type(e).__name__)


def drop_atlas_db() -> None:
    try:
        client = common.get_mongo_client()
        client.drop_database(common.DB_NAME)
        client.close()
        log.info("Dropped Atlas database %s", common.DB_NAME)
    except Exception as e:
        log.warning("Skip Atlas drop: %s", type(e).__name__)


def clear_state() -> None:
    common.clear_resume_token()
    (common.STATE_DIR / "live_order.json").unlink(missing_ok=True)
    log.info("Cleared local checkpoint/state files")


def main() -> None:
    common.banner("RESET · remove demo data (idempotent)")
    drop_iceberg()
    empty_bucket()
    drop_atlas_db()
    clear_state()
    log.info("Reset complete. Infra still running (use `make down` to stop it).")


if __name__ == "__main__":
    main()
