"""Tests for schema validation — fields forced by account type.

Offline: the MongoDB `$jsonSchema` validator is converted to plain JSON
Schema (`to_json_schema`) and checked with the `jsonschema` package, so no
server is needed. mongomock does not enforce `$jsonSchema`, so the
server-side application of the validator is exercised through the schema
documents themselves.

Run: python3 -m pytest tests -v
"""

from __future__ import annotations

import mongomock
import pytest
from jsonschema import Draft202012Validator

from lib.cap_service import process_ingest
from lib.sample_data import account_docs
from lib.schema_validation import (ACCOUNT_VALIDATOR, ACCOUNT_TYPES,
                                   to_json_schema)


@pytest.fixture(scope="module")
def validator():
    return Draft202012Validator(to_json_schema(ACCOUNT_VALIDATOR["$jsonSchema"]))


def test_every_seeded_account_validates(validator):
    for doc in account_docs():
        errors = sorted(validator.iter_errors(dict(doc)),
                        key=lambda e: e.path)
        assert not errors, f"{doc['accountId']}: " + "; ".join(
            f"{list(e.path)}: {e.message}" for e in errors)


def test_account_type_is_required_and_constrained(validator):
    bad = dict(account_docs()[0], accountType="platinum")
    assert validator.is_valid(dict(bad)) is False
    del bad["accountType"]
    assert validator.is_valid(bad) is False


def test_smb_requires_service_package_fields(validator):
    # Drop the package from an SMB account → must fail.
    smb = dict(account_docs()[0])
    smb["serviceData"] = {}
    assert not validator.is_valid(smb)
    # Package missing `cap` → must fail.
    smb2 = dict(account_docs()[0])
    smb2["serviceData"] = {"servicePackage": {"packageId": "PKG-SMB-100",
                                              "capType": "local_tn"}}
    assert not validator.is_valid(smb2)
    # Cap below 1 → must fail.
    smb3 = dict(account_docs()[0])
    smb3["serviceData"] = {"servicePackage": {"packageId": "PKG-SMB-100",
                                              "capType": "local_tn",
                                              "cap": 0}}
    assert not validator.is_valid(smb3)


def test_enterprise_may_omit_service_package(validator):
    legacy = dict(account_docs()[3])  # ACC-ENT-0001 has serviceData: {}
    assert legacy["accountType"] == "enterprise"
    assert validator.is_valid(legacy)


def test_account_id_pattern_enforced(validator):
    bad = dict(account_docs()[0], accountId="CUST-77")
    assert not validator.is_valid(bad)


def test_account_types_are_generic_labels():
    assert ACCOUNT_TYPES == ["smb", "enterprise"]


def test_packageless_account_skips_cap_path(db):
    """Accounts without a service package flow through uncapped (the
    current behavior), per the alignment decision."""
    db["accounts"].insert_one({
        "accountId": "ACC-ENT-0001", "name": "Meridian Holdings",
        "accountType": "enterprise", "serviceData": {},
        "note": "synthetic demo data"})
    res = process_ingest(db, "ACC-ENT-0001",
                         [{"tn": "+15555550140", "type": "local"}], "portal")
    assert res.accepted
    assert db["numberAssets"].count_documents({"accountId": "ACC-ENT-0001"}) == 1
    # No counter created for a package-less account.
    assert db["provisioningCounters"].count_documents({}) == 0
