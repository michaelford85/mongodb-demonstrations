"""Multi-document transaction behavior tests.

Proves the core claim: a simulated failure mid-transaction rolls back *both*
writes, and a successful run persists both. Runs against a throwaway test
database on the connected Atlas cluster and drops it afterward. Skips cleanly
when no replica-set cluster is reachable.
"""

import pytest

from lib.atlas_client import get_client, ping
from lib.transactions import change_plan

TEST_DB = "croptrace_demo_txn_test"


def _supports_transactions() -> bool:
    if not ping():
        return False
    try:
        hello = get_client().admin.command("hello")
        return bool(hello.get("setName"))  # replica set required for txns
    except Exception:
        return False


@pytest.fixture()
def seeded_treatment():
    client = get_client()
    db = client[TEST_DB]
    db.treatment_events.drop()
    db.audit_events.drop()
    db.treatment_events.insert_one({
        "treatment_id": "TRT-TEST-1", "plot_id": "PLOT-001",
        "product_ref": "CPP-001", "status": "planned", "dose_l_per_ha": 0.5})
    yield client
    client.drop_database(TEST_DB)


@pytest.mark.skipif(not _supports_transactions(),
                    reason="Atlas replica set not reachable")
def test_simulated_failure_rolls_back_both_writes(seeded_treatment):
    client = seeded_treatment
    db = client[TEST_DB]
    res = change_plan(client, TEST_DB, treatment_id="TRT-TEST-1",
                      new_status="applied", new_dose=1.2, fail=True)
    assert res["committed"] is False
    assert res["audit_persisted"] is False
    # Neither write persisted: status is still the seeded value.
    assert db.treatment_events.find_one(
        {"treatment_id": "TRT-TEST-1"})["status"] == "planned"
    assert db.audit_events.count_documents({}) == 0


@pytest.mark.skipif(not _supports_transactions(),
                    reason="Atlas replica set not reachable")
def test_successful_run_persists_both_writes(seeded_treatment):
    client = seeded_treatment
    db = client[TEST_DB]
    res = change_plan(client, TEST_DB, treatment_id="TRT-TEST-1",
                      new_status="applied", new_dose=1.2, fail=False)
    assert res["committed"] is True
    assert res["audit_persisted"] is True
    assert db.treatment_events.find_one(
        {"treatment_id": "TRT-TEST-1"})["status"] == "applied"
    assert db.audit_events.count_documents(
        {"treatment_id": "TRT-TEST-1"}) == 1
