"""Schema validation for the accounts collection — fields forced by account
type.

Design (from the walkthrough discussion): SMB and non-SMB accounts live in
the SAME collection. A new `accountType` field ("smb" | "enterprise") marks
the account's segment, and the validator enforces segment-specific fields:

* every account must have `accountId`, `name`, and `accountType`;
* an SMB account MUST carry a service package (`serviceData.servicePackage`)
  with `packageId`, `capType`, and a numeric `cap` — this is what drives the
  cap-enforcement path;
* an enterprise account MAY omit the package entirely (the existing flow).

The validator is MongoDB-flavored `$jsonSchema`. `apply_account_validator`
installs it on the demo `accounts` collection behind an explicit UI button.
`to_json_schema` converts it to plain JSON Schema so offline tests (and any
JSON-Schema tooling) can validate documents without a server.
"""

from __future__ import annotations

from pymongo.database import Database

from lib.config import ACCOUNTS_COLLECTION

ACCOUNT_TYPE_FIELD = "accountType"
ACCOUNT_TYPES = ["smb", "enterprise"]
CAP_TYPES = ["local_tn"]

ACCOUNT_VALIDATOR = {
    "$jsonSchema": {
        "title": "account-by-type",
        "bsonType": "object",
        "required": ["accountId", "name", "accountType"],
        "properties": {
            "accountId": {"bsonType": "string", "pattern": "^ACC-"},
            "name": {"bsonType": "string"},
            "accountType": {"enum": ACCOUNT_TYPES},
            "parentAccount": {"bsonType": ["string", "array", "null"]},
            "superAccount": {"bsonType": ["string", "null"]},
            "featureData": {"bsonType": "object"},
            "serviceData": {"bsonType": "object"},
            "billing": {"bsonType": "object"},
            "vetting": {"bsonType": "object"},
            "note": {"bsonType": "string"},
        },
        "additionalProperties": True,
        # ── Fields forced BY ACCOUNT TYPE ──────────────────────────────────
        "allOf": [
            {
                "if": {"properties": {"accountType": {"enum": ["smb"]}},
                       "required": ["accountType"]},
                "then": {
                    "properties": {
                        "serviceData": {
                            "required": ["servicePackage"],
                            "properties": {
                                "servicePackage": {
                                    "bsonType": "object",
                                    "required": ["packageId", "capType",
                                                 "cap"],
                                    "properties": {
                                        "packageId": {"bsonType": "string"},
                                        "capType": {"enum": CAP_TYPES},
                                        "cap": {"bsonType":
                                                ["int", "long", "double",
                                                 "decimal"],
                                                "minimum": 1},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            {
                "if": {"properties": {"accountType": {"enum": ["enterprise"]}},
                       "required": ["accountType"]},
                "then": {"properties": {
                    "billing": {"properties": {
                        "tier": {"enum": ["enterprise", "smb_trial",
                                          "legacy"]}}}}},
            },
        ],
    }
}

# BSON type names → JSON Schema type names (for offline validation).
_BSON_TO_JSON = {
    "object": "object", "string": "string", "array": "array",
    "null": "null", "bool": "boolean",
    "int": "number", "long": "number", "double": "number",
    "decimal": "number",
}


def to_json_schema(schema: dict) -> dict:
    """Convert a MongoDB `$jsonSchema` document into plain JSON Schema so it
    can be validated offline with the `jsonschema` package."""
    out: dict = {}
    for key, value in schema.items():
        if key == "bsonType":
            if isinstance(value, list):
                types = sorted(_BSON_TO_JSON.get(t, t) for t in value)
                if types == ["null", "number"]:
                    out["type"] = ["number", "null"]
                elif types == ["null", "string"]:
                    out["type"] = ["string", "null"]
                else:
                    out["type"] = types[0] if len(types) == 1 else types
            else:
                out["type"] = _BSON_TO_JSON.get(value, value)
        elif key == "$jsonSchema":
            out.update(to_json_schema(value))
        elif isinstance(value, dict):
            out[key] = to_json_schema(value)
        elif isinstance(value, list):
            out[key] = [to_json_schema(v) if isinstance(v, dict) else v
                        for v in value]
        else:
            out[key] = value
    return out


def apply_account_validator(db: Database,
                            validation_action: str = "error") -> dict:
    """Install the account validator on the demo collection. Idempotent via
    `collMod` (creates the collection if needed). Writes only to the demo
    database."""
    if ACCOUNTS_COLLECTION not in db.list_collection_names():
        db.create_collection(
            ACCOUNTS_COLLECTION, validator=ACCOUNT_VALIDATOR,
            validationAction=validation_action, validationLevel="strict")
    else:
        db.command({
            "collMod": ACCOUNTS_COLLECTION,
            "validator": ACCOUNT_VALIDATOR,
            "validationAction": validation_action,
            "validationLevel": "strict",
        })
    return {"collection": ACCOUNTS_COLLECTION,
            "validationAction": validation_action}
