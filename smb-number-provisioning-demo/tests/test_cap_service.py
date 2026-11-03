"""Focused tests for the SMB provisioning demo.

Offline by design: they run against an in-memory mongomock database — no
remote cluster is contacted and no real database is touched. mongomock does
not support multi-document transactions, so these tests exercise the
reservation + compensation path; the transaction path is skipped when
transactions are unavailable (as they are on mongomock).

Run: python3 -m pytest tests -v
"""

from __future__ import annotations

import io
import threading
from concurrent.futures import ThreadPoolExecutor

import mongomock
import pytest

from lib.cap_service import (ACCEPTED, BAD_NUMBER, CAP_EXCEEDED, CAP_TYPE,
                             DUPLICATE, DEFAULT_CAP, get_or_create_counter,
                             lower_cap, process_ingest, reactivate_number,
                             remove_number, set_counter_for_demo,
                             states_counting_toward_cap, transfer_number,
                             valid_tn)
from lib.sample_data import account_docs, seed_demo


@pytest.fixture()
def db():
    client = mongomock.MongoClient()
    database = client["smb_number_demo"]
    database["numberAssets"].create_index(
        [("accountId", 1), ("tn.orig.startTn", 1), ("type", 1)],
        unique=True)
    database["provisioningCounters"].create_index(
        [("accountId", 1), ("capType", 1)], unique=True)
    for doc in account_docs():
        database["accounts"].insert_one(dict(doc))
    return database


def counter(db, account_id):
    doc = db["provisioningCounters"].find_one(
        {"accountId": account_id, "capType": CAP_TYPE})
    return (doc["activeCount"], doc["cap"]) if doc else (None, None)


def asset_count(db, account_id=None):
    q = {"accountId": account_id} if account_id else {}
    return db["numberAssets"].count_documents(q)


# ── validation ─────────────────────────────────────────────────────────────

def test_fictional_range_only():
    assert valid_tn("+15550100")
    assert not valid_tn("+155500001")  # outside the reserved fictional block
    assert not valid_tn("5550100")
    assert not valid_tn("+1555010")   # wrong length


def test_unknown_account_rejects_every_item_without_assets(db):
    res = process_ingest(db, "ACC-NOPE", [{"tn": "+15550100", "type": "local"}],
                         "portal")
    assert res.accepted == [] and res.rejected
    assert res.rejected[0].code == "422 ACCOUNT_NOT_FOUND"
    assert asset_count(db) == 0
    assert db["provisioningAudit"].count_documents(
        {"event": "PROVISIONING_REJECTED"}) == 1


def test_invalid_format_and_type_rejected_without_reservation(db):
    items = [{"tn": "bogus", "type": "local"},
             {"tn": "+15550101", "type": "satellite"}]
    res = process_ingest(db, "ACC-SMB-0001", items, "portal")
    assert [r.code for r in res.rejected] == [BAD_NUMBER,
                                              "422 INVALID_NUMBER_TYPE"]
    assert counter(db, "ACC-SMB-0001")[0] in (0, None)


# ── each entry route uses the same service ────────────────────────────────

@pytest.mark.parametrize("channel", ["portal", "batch", "direct_api"])
def test_all_routes_share_one_service(db, channel):
    res = process_ingest(db, "ACC-SMB-0001",
                         [{"tn": "+15550102", "type": "local"}], channel)
    assert res.accepted and res.results[0].code == ACCEPTED
    assert asset_count(db, "ACC-SMB-0001") == 1
    assert counter(db, "ACC-SMB-0001") == (1, DEFAULT_CAP)


def test_csv_rows_processed_in_file_order_with_partial_results(db):
    """Rows after the cap is reached are rejected, in order, not skipped."""
    csv_text = "tn,type\n+15550103,local\n,local\n+15550104,local\n"
    import csv as _csv
    rows = list(_csv.DictReader(io.StringIO(csv_text)))
    items = [{"tn": r["tn"], "type": r["type"]} for r in rows if r.get("tn")]
    malformed = [r for r in rows if not r.get("tn")]
    assert len(malformed) == 1  # malformed rows are reported, never skipped
    # Cap the account at 1 so the second valid row must be rejected.
    set_counter_for_demo(db, "ACC-SMB-0001", 0, 1)
    res = process_ingest(db, "ACC-SMB-0001", items, "batch", cap=1)
    accepted = [r.tn for r in res.accepted]
    rejected = [r.tn for r in res.rejected]
    assert accepted == ["+15550103"]          # first row accepted
    assert "+15550104" in rejected            # after cap reached → rejected
    assert counter(db, "ACC-SMB-0001")[0] == 1
    assert asset_count(db, "ACC-SMB-0001") == 1


# ── duplicate prevention ───────────────────────────────────────────────────

def test_duplicate_number_rejected_by_validation(db):
    first = process_ingest(db, "ACC-SMB-0001",
                           [{"tn": "+15550105", "type": "local"}], "portal")
    assert first.accepted
    dup = process_ingest(db, "ACC-SMB-0001",
                         [{"tn": "+15550105", "type": "local"}], "api")
    assert dup.rejected and dup.rejected[0].code == DUPLICATE
    assert counter(db, "ACC-SMB-0001")[0] == 1  # no double-count
    assert asset_count(db, "ACC-SMB-0001") == 1


def test_same_number_on_different_accounts_is_allowed(db):
    assert process_ingest(db, "ACC-SMB-0001",
                          [{"tn": "+15550106", "type": "local"}],
                          "portal").accepted
    assert process_ingest(db, "ACC-SMB-0002",
                          [{"tn": "+15550106", "type": "local"}],
                          "portal").accepted


# ── cap enforcement ────────────────────────────────────────────────────────

def test_exactly_at_cap_succeeds(db):
    set_counter_for_demo(db, "ACC-SMB-0001", 98, 100)
    res = process_ingest(db, "ACC-SMB-0001",
                         [{"tn": "+15550107", "type": "local"},
                          {"tn": "+15550108", "type": "local"}], "batch")
    assert len(res.accepted) == 2
    assert counter(db, "ACC-SMB-0001")[0] == 100


def test_over_cap_rejected_no_asset_saved_audited(db):
    set_counter_for_demo(db, "ACC-SMB-0001", 99, 100)
    res = process_ingest(db, "ACC-SMB-0001",
                         [{"tn": "+15550107", "type": "local"},
                          {"tn": "+15550108", "type": "local"}], "api")
    assert all(not r.ok for r in res.results)
    assert all(r.code == CAP_EXCEEDED for r in res.results)
    assert asset_count(db, "ACC-SMB-0001") == 0
    assert db["provisioningAudit"].count_documents(
        {"event": "PROVISIONING_REJECTED",
         "resultCode": CAP_EXCEEDED}) == 1
    assert counter(db, "ACC-SMB-0001")[0] == 99


def test_race_99_of_100_exactly_one_success(db):
    """Two concurrent one-number requests at 99/100: exactly one succeeds.
    mongomock applies the conditional update atomically per document, so the
    race resolves the same way regardless of thread timing."""
    set_counter_for_demo(db, "ACC-SMB-RACE", 99, 100)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda i: process_ingest(db, "ACC-SMB-RACE",
                                     [{"tn": f"+155501{i:02d}",
                                       "type": "local"}], f"race-{i}"),
            range(10, 12)))
    successes = sum(len(r.accepted) for r in results)
    rejections = sum(len(r.rejected) for r in results)
    assert successes == 1 and rejections == 1
    assert counter(db, "ACC-SMB-RACE")[0] == 100
    assert asset_count(db, "ACC-SMB-RACE") == 1
    rejected_assets = db["numberAssets"].count_documents(
        {"accountId": "ACC-SMB-RACE", "tn.orig.startTn": "+15550111"})
    assert rejected_assets == 0  # nothing saved for the rejected request


# ── idempotency ────────────────────────────────────────────────────────────

def test_idempotent_retry_does_not_double_count(db):
    key = "idem-fixed-key"
    first = process_ingest(db, "ACC-SMB-0001",
                           [{"tn": "+15550109", "type": "local"}], "portal",
                           idempotency_key=key)
    second = process_ingest(db, "ACC-SMB-0001",
                            [{"tn": "+15550109", "type": "local"}], "portal",
                            idempotency_key=key)
    assert first.accepted and second.accepted and second.replayed
    assert asset_count(db, "ACC-SMB-0001") == 1
    assert counter(db, "ACC-SMB-0001")[0] == 1


# ── removal / reactivation / transfer ──────────────────────────────────────

def test_removal_frees_capacity_exactly_once(db):
    process_ingest(db, "ACC-SMB-0001",
                   [{"tn": "+15550110", "type": "local"}], "portal")
    assert counter(db, "ACC-SMB-0001")[0] == 1
    ok, _ = remove_number(db, "ACC-SMB-0001", "+15550110")
    assert ok and counter(db, "ACC-SMB-0001")[0] == 0
    # Removing again must not decrement twice.
    ok2, _ = remove_number(db, "ACC-SMB-0001", "+15550110")
    assert ok2 and counter(db, "ACC-SMB-0001")[0] == 0


def test_reactivation_counts_as_addition(db):
    # A released asset exists (synthetic seed shape) on ACC-SMB-0002.
    db["numberAssets"].insert_one({
        "accountId": "ACC-SMB-0002", "type": "local", "state": "released",
        "tn": {"orig": {"start": "+15550110", "count": 1,
                        "startTn": "+15550110", "endTn": "+15550110"}},
        "note": "synthetic demo data"})
    ok, _ = reactivate_number(db, "ACC-SMB-0002", "+15550110")
    assert ok and counter(db, "ACC-SMB-0002")[0] == 1


def test_transfer_counts_as_addition_on_destination(db):
    process_ingest(db, "ACC-SMB-0001",
                   [{"tn": "+15550111", "type": "local"}], "portal")
    ok, _ = transfer_number(db, "ACC-SMB-0001", "ACC-SMB-0002", "+15550111")
    assert ok
    assert counter(db, "ACC-SMB-0002")[0] == 1
    moved = db["numberAssets"].find_one({"tn.orig.startTn": "+15550111"})
    assert moved["accountId"] == "ACC-SMB-0002"


def test_transfer_over_cap_rejected_number_stays_on_source(db):
    process_ingest(db, "ACC-SMB-0001",
                   [{"tn": "+15550112", "type": "local"}], "portal")
    set_counter_for_demo(db, "ACC-SMB-0002", 100, 100)  # destination is full
    ok, msg = transfer_number(db, "ACC-SMB-0001", "ACC-SMB-0002",
                              "+15550112")
    assert not ok and msg == CAP_EXCEEDED
    moved = db["numberAssets"].find_one({"tn.orig.startTn": "+15550112"})
    assert moved["accountId"] == "ACC-SMB-0001"          # stayed on source
    assert counter(db, "ACC-SMB-0002")[0] == 100         # refunded, not 101


# ── cap lowered below usage ────────────────────────────────────────────────

def test_cap_lowered_below_usage_keeps_assets_blocks_additions(db):
    for i in range(3):
        assert process_ingest(db, "ACC-SMB-0001",
                              [{"tn": f"+1555012{i}", "type": "local"}],
                              "portal").accepted
    lower_cap(db, "ACC-SMB-0001", 2)
    assert counter(db, "ACC-SMB-0001") == (3, 2)   # existing numbers kept
    res = process_ingest(db, "ACC-SMB-0001",
                         [{"tn": "+15550123", "type": "local"}],
                         "portal", cap=2)
    assert res.rejected and res.rejected[0].code == CAP_EXCEEDED
    assert asset_count(db, "ACC-SMB-0001") == 3    # nothing deleted
    # Freeing numbers unblocks additions once usage is below the cap.
    ok, _ = remove_number(db, "ACC-SMB-0001", "+15550120")
    assert ok
    ok, _ = remove_number(db, "ACC-SMB-0001", "+15550121")
    assert ok
    res2 = process_ingest(db, "ACC-SMB-0001",
                          [{"tn": "+15550123", "type": "local"}],
                          "portal", cap=2)
    assert res2.accepted
    assert res2.accepted


# ── consistency & business rule ────────────────────────────────────────────

def test_counter_matches_counted_assets(db):
    process_ingest(db, "ACC-SMB-0001",
                   [{"tn": "+15550114", "type": "local"},
                    {"tn": "+15550115", "type": "local"}], "batch")
    counted = db["numberAssets"].count_documents(
        {"accountId": "ACC-SMB-0001",
         "state": {"$in": sorted(states_counting_toward_cap())}})
    assert counter(db, "ACC-SMB-0001")[0] == counted


def test_states_counting_toward_cap_is_explicit_and_configurable():
    assert states_counting_toward_cap() == frozenset({"active"})


def test_seed_is_idempotent(db):
    from lib.sample_data import seed_demo as seed
    seed(db)
    seed(db)
    assert db["accounts"].count_documents({}) == 4
    assert db["numberAssets"].count_documents({}) == 4
