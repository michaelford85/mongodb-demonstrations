"""Multi-document transaction workflow for the CropTrace demo.

Scenario: a grower changes a treatment plan (status/dose on `treatment_events`)
*and* an audit/event record is written to `audit_events`. The two writes must
either both commit or both roll back. This uses a session-scoped transaction so
we can inject a deliberate failure after the first write and show that neither
change persisted.

The honest caveat: MongoDB fully supports multi-document transactions, but a
good document model keeps most ordinary operations single-document — reach for
a transaction when two independent documents must change atomically, as here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pymongo import MongoClient
from pymongo.database import Database


class SimulatedFailure(RuntimeError):
    """Raised on purpose mid-transaction to demonstrate atomic rollback."""


def get_treatment(db: Database, treatment_id: str) -> dict | None:
    return db.treatment_events.find_one({"treatment_id": treatment_id},
                                        {"_id": 0})


def list_audit_events(db: Database, plot_id: str, limit: int = 20) -> list[dict]:
    return list(db.audit_events.find({"plot_id": plot_id}, {"_id": 0})
                .sort("created_at", -1).limit(limit))


def audit_count(db: Database) -> int:
    return db.audit_events.count_documents({})


def change_plan(client: MongoClient, db_name: str, *, treatment_id: str,
                new_status: str, new_dose: float, actor: str = "grower",
                fail: bool = False) -> dict:
    """Change a treatment and write a linked audit event in one transaction.

    When `fail=True`, a SimulatedFailure is raised *after* the treatment update
    but *before* commit, so the transaction aborts and neither write persists.
    Returns a small result dict describing what happened for the UI.
    """
    db = client[db_name]
    before = get_treatment(db, treatment_id)
    if not before:
        raise ValueError(f"treatment '{treatment_id}' not found — seed first")

    now = datetime.now(timezone.utc)
    audit_doc = {
        "audit_id": "AUD-" + now.strftime("%Y%m%d%H%M%S%f"),
        "plot_id": before["plot_id"], "treatment_id": treatment_id,
        "action": "treatment_plan_changed", "actor": actor,
        "from_status": before.get("status"), "to_status": new_status,
        "created_at": now,
    }

    committed = False
    with client.start_session() as session:
        try:
            with session.start_transaction():
                db.treatment_events.update_one(
                    {"treatment_id": treatment_id},
                    {"$set": {"status": new_status, "dose_l_per_ha": new_dose}},
                    session=session)
                if fail:
                    # Deliberate failure between the two writes → abort.
                    raise SimulatedFailure(
                        "Simulated downstream error after the treatment update")
                db.audit_events.insert_one(audit_doc, session=session)
            committed = True
        except SimulatedFailure:
            # Transaction already aborted by the context manager on exception.
            committed = False

    after = get_treatment(db, treatment_id)
    return {
        "committed": committed,
        "simulated_failure": fail,
        "treatment_before": before,
        "treatment_after": after,
        "audit_doc": audit_doc if committed else None,
        "audit_persisted": db.audit_events.count_documents(
            {"audit_id": audit_doc["audit_id"]}) == 1,
    }
