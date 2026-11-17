#!/usr/bin/env python3
"""Seed the synthetic PostgreSQL demo schema and emit CDC events.

Examples:
    python scripts/seed_postgres.py --count 20          # initial snapshot rows
    python scripts/seed_postgres.py --update-id 3       # triggers an UPDATE CDC event
    python scripts/seed_postgres.py --delete-id 5       # triggers a DELETE CDC event

Requires network reachability to the RDS instance (from inside the VPC, or
set local_ingress_cidr in Terraform and run locally). PG_* values come from .env.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).parent))
from common import load_config  # noqa: E402

TITLES = [
    "Resetting your workspace password",
    "Requesting hardware upgrades",
    "Understanding quarterly reporting cycles",
    "Submitting travel reimbursement forms",
    "Configuring the analytics dashboard",
    "Onboarding checklist for new team members",
    "Using the internal wiki effectively",
    "Escalating security incidents",
    "Scheduling shared meeting rooms",
    "Exporting data from the reporting tool",
    "Managing VPN profiles on mobile devices",
    "Updating project documentation standards",
    "Troubleshooting slow report exports",
    "Archiving finished project workspaces",
    "Reviewing access request workflows",
]

BODIES = [
    "This article explains the step-by-step process, expected turnaround time, "
    "and who to contact when the request is stuck in review.",
    "A short walkthrough covering prerequisites, common pitfalls, and links to "
    "related runbooks for deeper troubleshooting.",
    "Summarizes policy highlights with worked examples so application users can "
    "self-serve without opening a ticket.",
    "Describes the underlying data flow, refresh cadence, and the fields that "
    "matter most when validating results.",
    "Covers the approval chain, required attachments, and typical failure modes "
    "with their resolutions.",
]
DEPARTMENTS = ["it", "hr", "finance", "operations", "general"]
FAQ_QA = [
    "Where do I find the monthly close calendar?",
    "How do I restore a deleted document from the archive?",
    "What is the escalation path for a lost laptop?",
    "Which role approves purchase requests above the threshold?",
]


def connect(cfg: dict):
    return psycopg2.connect(
        host=cfg["pg"]["host"],
        port=cfg["pg"]["port"],
        dbname=cfg["pg"]["dbname"],
        user=cfg["pg"]["user"],
        password=cfg["pg"]["password"],
        sslmode="require",
        connect_timeout=15,
    )


def provision_schema(conn, cfg: dict, cdc_user: str | None) -> None:
    schema = cfg["pg"]["schema"]
    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {schema}.knowledge_items (
                id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                entity_type  TEXT        NOT NULL CHECK (entity_type IN ('article', 'faq')),
                title        TEXT        NOT NULL,
                body         TEXT        NOT NULL,
                tags         TEXT        NOT NULL DEFAULT '',
                department   TEXT        NOT NULL DEFAULT 'general',
                author       TEXT        NOT NULL DEFAULT 'demo-author',
                is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS knowledge_items_type_idx "
            f"ON {schema}.knowledge_items (entity_type)"
        )
        cur.execute(
            f"ALTER TABLE {schema}.knowledge_items REPLICA IDENTITY FULL"
        )
        if cdc_user:
            # DMS CDC needs replication rights on the source table.
            cur.execute(f"GRANT USAGE ON SCHEMA {schema} TO {cdc_user}")
            cur.execute(
                f"GRANT SELECT ON {schema}.knowledge_items TO {cdc_user}"
            )
    conn.commit()


def insert_rows(conn, cfg: dict, count: int) -> list[int]:
    schema = cfg["pg"]["schema"]
    rng = random.Random(42)
    ids = []
    with conn.cursor() as cur:
        for i in range(count):
            etype = "faq" if i % 4 == 0 else "article"
            title = (
                rng.choice(FAQ_QA)
                if etype == "faq"
                else rng.choice(TITLES)
            )
            body = rng.choice(BODIES)
            tags = ",".join(rng.sample(["howto", "policy", "it", "self-serve", "reporting"], 2))
            dept = rng.choice(DEPARTMENTS)
            cur.execute(
                f"INSERT INTO {schema}.knowledge_items "
                f"(entity_type, title, body, tags, department) "
                f"VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (etype, title, body, tags, dept),
            )
            ids.append(cur.fetchone()[0])
    conn.commit()
    return ids


def update_row(conn, cfg: dict, row_id: int) -> None:
    schema = cfg["pg"]["schema"]
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {schema}.knowledge_items SET title = title || ' (revised)', "
            f"body = body || ' Updated: reviewed for accuracy in the current release cycle.', "
            f"updated_at = now() WHERE id = %s",
            (row_id,),
        )
        if cur.rowcount == 0:
            conn.rollback()
            raise SystemExit(f"No row with id={row_id}")
    conn.commit()


def delete_row(conn, cfg: dict, row_id: int) -> None:
    schema = cfg["pg"]["schema"]
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {schema}.knowledge_items WHERE id = %s", (row_id,))
        if cur.rowcount == 0:
            conn.rollback()
            raise SystemExit(f"No row with id={row_id}")
    conn.commit()


def main() -> None:
    cfg = load_config()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=None, help="Rows to insert (snapshot data). No-arg run only provisions the schema.")
    parser.add_argument("--update-id", type=int, help="Update this row to emit an UPDATE CDC event.")
    parser.add_argument("--delete-id", type=int, help="Delete this row to emit a DELETE CDC event.")
    parser.add_argument("--cdc-user", default=None, help="Also grant SELECT to this DMS CDC role.")
    args = parser.parse_args()

    conn = connect(cfg)
    try:
        if args.count:
            ids = insert_rows(conn, cfg, args.count)
            print(f"Inserted {len(ids)} rows: {ids}")
        if args.update_id:
            update_row(conn, cfg, args.update_id)
            print(f"Updated row {args.update_id} (UPDATE CDC event emitted).")
        if args.delete_id:
            delete_row(conn, cfg, args.delete_id)
            print(f"Deleted row {args.delete_id} (DELETE CDC event emitted).")
        if not (args.count or args.update_id or args.delete_id):
            provision_schema(conn, cfg, args.cdc_user)
            print("Schema provisioned. Re-run with --count to insert rows.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
