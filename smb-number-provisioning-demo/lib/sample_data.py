"""Synthetic seed data — every value here is invented for the demonstration.

Accounts, brands, and telephone numbers are fictional. Telephone numbers are
drawn from the fictional 555/555 exchange (+1555555xxxx). No real
company, customer, or personal data is used.
"""

from __future__ import annotations

from lib.config import (ACCOUNTS_COLLECTION, NUMBER_ASSETS_COLLECTION,
                        RACE_ACCOUNT_ID)
from lib.cap_service import (CAP_TYPE, DEFAULT_CAP, TN_PATTERN, _now,
                             get_or_create_counter)

# Full-length fictional US numbers: area code 555, exchange 555 — never
# assigned to real subscribers. Enough addresses for stress tests.
FICTIONAL_TNS = [f"+1555555{n:04d}" for n in range(100, 5100)]
assert all(TN_PATTERN.match(t) for t in FICTIONAL_TNS)


def account_docs() -> list[dict]:
    return [
        {
            "accountId": "ACC-SMB-0001", "name": "Bright Harbor Dental",
            "parentAccount": "ACC-ENT-0042", "superAccount": "ACC-ENT-0001",
            "featureData": {"brandedCalling": True, "logoRef": "synthetic-logo-1"},
            "serviceData": {"servicePackage": {"packageId": "PKG-SMB-100",
                                               "capType": CAP_TYPE,
                                               "cap": DEFAULT_CAP}},
            "billing": {"tier": "smb_trial", "currency": "USD",
                        "synthetic": True},
            "vetting": {"status": "not_verified_demo_only"},
            "note": "synthetic demo data",
        },
        {
            "accountId": "ACC-SMB-0002", "name": "Cedar & Sloe Coffee",
            "parentAccount": None, "superAccount": None,
            "featureData": {"brandedCalling": False, "logoRef": None},
            "serviceData": {"servicePackage": {"packageId": "PKG-SMB-100",
                                               "capType": CAP_TYPE,
                                               "cap": DEFAULT_CAP}},
            "billing": {"tier": "smb_trial", "currency": "USD",
                        "synthetic": True},
            "vetting": {"status": "not_verified_demo_only"},
            "note": "synthetic demo data",
        },
        {
            "accountId": "ACC-ENT-0042", "name": "Northwind Retail Group",
            "parentAccount": "ACC-ENT-0001", "superAccount": None,
            "featureData": {"brandedCalling": True, "logoRef": "synthetic-logo-2"},
            "serviceData": {"servicePackage": {"packageId": "PKG-ENT-5000",
                                               "capType": CAP_TYPE,
                                               "cap": 5000}},
            "billing": {"tier": "enterprise", "currency": "USD",
                        "synthetic": True},
            "vetting": {"status": "not_verified_demo_only"},
            "note": "synthetic demo data",
        },
        {
            "accountId": RACE_ACCOUNT_ID, "name": "Race Rehearsal Account",
            "parentAccount": None, "superAccount": None,
            "featureData": {"brandedCalling": False, "logoRef": None},
            "serviceData": {"servicePackage": {"packageId": "PKG-SMB-100",
                                               "capType": CAP_TYPE,
                                               "cap": DEFAULT_CAP}},
            "billing": {"tier": "smb_trial", "currency": "USD",
                        "synthetic": True},
            "vetting": {"status": "not_verified_demo_only"},
            "note": "synthetic demo data; used for the 99/100 concurrency race",
        },
    ]


def existing_asset_docs() -> list[dict]:
    """A few pre-existing assets so capacity pages have context."""
    docs = []
    for i, tn in enumerate(FICTIONAL_TNS[:3]):
        docs.append({
            "accountId": "ACC-SMB-0001",
            "parentAccountId": "ACC-ENT-0042", "superAccountId": "ACC-ENT-0001",
            "type": "local", "state": "active",
            "tn": {"orig": {"start": tn, "count": 1, "startTn": tn,
                            "endTn": tn}},
            "callerProfileId": f"cp-seed{i:03d}",
            "partnerData": {"synthetic": True},
            "vetting": {"status": "not_verified_demo_only"},
            "note": "synthetic demo data",
        })
    # One released number on ACC-SMB-0002 for the reactivation example.
    docs.append({
        "accountId": "ACC-SMB-0002", "parentAccountId": None,
        "superAccountId": None, "type": "local", "state": "released",
        "tn": {"orig": {"start": FICTIONAL_TNS[10], "count": 1,
                        "startTn": FICTIONAL_TNS[10],
                        "endTn": FICTIONAL_TNS[10]}},
        "callerProfileId": "cp-seed010",
        "partnerData": {"synthetic": True},
        "vetting": {"status": "not_verified_demo_only"},
        "note": "synthetic demo data",
    })
    return docs


def seed_demo(db) -> dict:
    """Idempotent seed of demo accounts, a few assets, and counters.
    Uses only upserts/updates on the demo database — never destructive."""
    for doc in account_docs():
        db[ACCOUNTS_COLLECTION].update_one(
            {"accountId": doc["accountId"]}, {"$setOnInsert": doc},
            upsert=True)
    for doc in existing_asset_docs():
        db[NUMBER_ASSETS_COLLECTION].update_one(
            {"accountId": doc["accountId"], "tn.orig.startTn":
             doc["tn"]["orig"]["startTn"], "type": doc["type"]},
            {"$setOnInsert": doc}, upsert=True)
    for acc in account_docs():
        get_or_create_counter(db, acc["accountId"],
                              acc["serviceData"]["servicePackage"]["cap"])
    return {"accounts": len(account_docs()),
            "assets": len(existing_asset_docs()), "at": _now().isoformat()}
