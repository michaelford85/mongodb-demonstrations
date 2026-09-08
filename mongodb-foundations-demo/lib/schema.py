"""JSON Schema validators for the three demo collections.

A flexible schema is not an absent schema. These `$jsonSchema` validators are
applied with `create` (or `collMod` when the collection already exists), so the
server enforces required fields, BSON types, value ranges, and allowed enum
values — while the document model is still free to evolve.

Deliberately basic: enough for a DBA to recognise NOT NULL, CHECK, and a domain
constraint, without turning the demo into a schema exercise. The validation
*level* and *action* differ per collection so both choices can be shown.
"""

from __future__ import annotations

from pymongo.database import Database
from pymongo.errors import OperationFailure

from lib.mongo_client import ACCOUNTS, CUSTOMERS, TRANSACTIONS
from lib.sample_data import (ACCOUNT_TYPES, CATEGORIES, CONTACT_CHANNELS,
                             LANGUAGES)

CUSTOMER_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "Customer profile",
        "required": ["customer_id", "name", "segment", "address", "contact"],
        "properties": {
            "customer_id": {"bsonType": "string",
                            "pattern": "^CUST-[0-9]{4}$"},
            "name": {
                "bsonType": "object",
                "required": ["first", "last"],
                "properties": {"first": {"bsonType": "string"},
                               "last": {"bsonType": "string"}},
            },
            "segment": {"enum": ["consumer", "small_business"]},
            "address": {
                "bsonType": "object",
                "required": ["city", "state", "postal_code", "country"],
                "properties": {"state": {"bsonType": "string",
                                         "pattern": "^[A-Z]{2}$"},
                               "postal_code": {"bsonType": "string"}},
            },
            "contact": {
                "bsonType": "object",
                "required": ["email"],
                "properties": {"email": {"bsonType": "string",
                                         "pattern": "^.+@.+$"}},
            },
            "preferences": {
                "bsonType": "object",
                "properties": {
                    "contact_channel": {"enum": CONTACT_CHANNELS},
                    "paperless": {"bsonType": "bool"},
                    "language": {"enum": LANGUAGES},
                },
            },
            "recent_alerts": {"bsonType": "array", "maxItems": 3},
        },
    }
}

ACCOUNT_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "Account",
        "required": ["account_number", "customer_id", "account_type", "status",
                     "currency", "balance"],
        "properties": {
            "account_number": {"bsonType": "string",
                               "pattern": "^ACCT-[0-9]{5}$"},
            "customer_id": {"bsonType": "string",
                            "pattern": "^CUST-[0-9]{4}$"},
            "account_type": {"enum": ACCOUNT_TYPES},
            "status": {"enum": ["open", "closed"]},
            "currency": {"enum": ["USD"]},
            "balance": {"bsonType": ["double", "int", "long"], "minimum": 0},
        },
    }
}

TRANSACTION_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "Posted transaction",
        "required": ["txn_id", "account_number", "category", "direction",
                     "amount", "posted_at"],
        "properties": {
            "txn_id": {"bsonType": "string"},
            "account_number": {"bsonType": "string",
                               "pattern": "^ACCT-[0-9]{5}$"},
            "category": {"enum": CATEGORIES},
            "direction": {"enum": ["debit", "credit"]},
            "amount": {"bsonType": ["double", "int", "long"],
                       "exclusiveMinimum": True, "minimum": 0},
            "posted_at": {"bsonType": "date"},
        },
    }
}

# Level and action are chosen per collection, and shown in the UI.
#   level  strict   → every insert and update is validated
#          moderate → existing documents that already fail are exempt on update
#   action error    → the write is rejected
#          warn     → the write succeeds and the server logs the violation
VALIDATORS = {
    CUSTOMERS: {"validator": CUSTOMER_VALIDATOR,
                "validationLevel": "strict", "validationAction": "error"},
    ACCOUNTS: {"validator": ACCOUNT_VALIDATOR,
               "validationLevel": "strict", "validationAction": "error"},
    TRANSACTIONS: {"validator": TRANSACTION_VALIDATOR,
                   "validationLevel": "moderate", "validationAction": "error"},
}


def apply_validators(db: Database) -> list:
    """Create or modify each demo collection so its validator is active.

    Idempotent: `collMod` when the collection exists, `create` when it does not.
    Returns the collection names whose validator was (re)applied.
    """
    applied = []
    existing = set(db.list_collection_names())
    for name, opts in VALIDATORS.items():
        command = {
            "validator": opts["validator"],
            "validationLevel": opts["validationLevel"],
            "validationAction": opts["validationAction"],
        }
        if name in existing:
            db.command({"collMod": name, **command})
        else:
            db.create_collection(name, **command)
        applied.append(name)
    return applied


def validator_info(db: Database, name: str) -> dict:
    """Return the validator and level/action the server currently holds."""
    for coll in db.list_collections(filter={"name": name}):
        opts = coll.get("options", {})
        return {
            "validator": opts.get("validator"),
            "validationLevel": opts.get("validationLevel"),
            "validationAction": opts.get("validationAction"),
        }
    return {}


def missing_validators(db: Database) -> list:
    """Collections that should carry a validator but currently do not."""
    return [name for name in VALIDATORS
            if not validator_info(db, name).get("validator")]


# One deliberately invalid document per collection, used to show the server
# rejecting a write. Each breaks exactly one stated rule.
REJECTED_EXAMPLES = {
    CUSTOMERS: {
        "rule": "`segment` must be one of consumer, small_business",
        "document": {"_id": "CUST-INVALID", "customer_id": "CUST-9999",
                     "name": {"first": "Test", "last": "Case"},
                     "segment": "wholesale",
                     "address": {"city": "Nowhere", "state": "ZZ",
                                 "postal_code": "00000", "country": "US"},
                     "contact": {"email": "test@example.invalid"}},
    },
    ACCOUNTS: {
        "rule": "`balance` must be a number and cannot be negative",
        "document": {"_id": "ACCT-INVALID", "account_number": "ACCT-99999",
                     "customer_id": "CUST-1001", "account_type": "checking",
                     "status": "open", "currency": "USD", "balance": -50.0},
    },
    TRANSACTIONS: {
        "rule": "`direction` must be debit or credit, and `posted_at` a date",
        "document": {"_id": "TXN-INVALID", "txn_id": "TXN-INVALID",
                     "account_number": "ACCT-50001", "category": "groceries",
                     "direction": "reversal", "amount": 10.0,
                     "posted_at": "2025-01-06"},
    },
}


def try_rejected_example(db: Database, name: str) -> dict:
    """Attempt the invalid insert for a collection and report the outcome.

    The document is designed to fail validation, so nothing is written. If the
    validator is missing and the write does succeed, it is removed immediately.
    """
    example = REJECTED_EXAMPLES[name]
    document = example["document"]
    try:
        db[name].insert_one(dict(document))
    except OperationFailure as exc:
        return {"rejected": True, "rule": example["rule"],
                "document": document, "code": exc.code,
                "error": str(exc), "details": (exc.details or {}).get("errInfo")}
    db[name].delete_one({"_id": document["_id"]})
    return {"rejected": False, "rule": example["rule"], "document": document,
            "code": None,
            "error": "The write was accepted — no validator is active on `{}`. "
                     "Re-seed to apply it.".format(name),
            "details": None}
