"""MongoDB JSON Schema validators for the CropTrace collections.

Flexible schema does not mean uncontrolled schema. These `$jsonSchema`
validators are applied with `collMod`/`create` so Atlas enforces required
fields, BSON types, and allowed enum values server-side — while still allowing
the document model to evolve. The validation *action* and *level* are chosen
deliberately per collection and surfaced in the UI.
"""

from __future__ import annotations

from pymongo.database import Database

from lib.atlas_client import (PRODUCT_CATEGORIES, RISK_LEVELS,
                              TREATMENT_STATUSES)

# ── Validator documents ─────────────────────────────────────────────────────

PLOT_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "CropTrace plot document",
        "required": ["plot_id", "grower_id", "crop", "region", "area_hectares"],
        "properties": {
            "plot_id": {"bsonType": "string", "pattern": "^PLOT-[0-9]{3}$"},
            "grower_id": {"bsonType": "string", "pattern": "^GRW-[0-9]{3}$"},
            "crop": {"bsonType": "string"},
            "region": {"bsonType": "string"},
            "area_hectares": {"bsonType": ["double", "int"], "minimum": 0},
            "treatments": {"bsonType": "array"},
            "weather_observations": {"bsonType": "array"},
            "residue_prediction": {"bsonType": ["object", "null"]},
        },
    }
}

PRODUCT_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "Crop-protection product (authoritative master data)",
        "required": ["product_id", "label_name", "category", "status"],
        "properties": {
            "product_id": {"bsonType": "string", "pattern": "^CPP-[0-9]{3}$"},
            "label_name": {"bsonType": "string"},
            "category": {"enum": PRODUCT_CATEGORIES},
            "status": {"enum": ["active", "restricted", "withdrawn"]},
            "reentry_interval_hours": {"bsonType": ["int", "double"], "minimum": 0},
            "phi_days": {"bsonType": ["int", "double"], "minimum": 0},
            "version": {"bsonType": ["int", "double"], "minimum": 1},
        },
    }
}

TREATMENT_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "Treatment event",
        "required": ["treatment_id", "plot_id", "product_ref", "status"],
        "properties": {
            "treatment_id": {"bsonType": "string"},
            "plot_id": {"bsonType": "string", "pattern": "^PLOT-[0-9]{3}$"},
            "product_ref": {"bsonType": "string", "pattern": "^CPP-[0-9]{3}$"},
            "status": {"enum": TREATMENT_STATUSES},
            "dose_l_per_ha": {"bsonType": ["double", "int"], "minimum": 0},
            "product_snapshot": {"bsonType": ["object", "null"]},
        },
    }
}

# Each validator is applied at a deliberate action/level, shown in the UI.
VALIDATORS = {
    "plots": {"validator": PLOT_VALIDATOR,
              "validationLevel": "moderate", "validationAction": "error"},
    "crop_protection_products": {"validator": PRODUCT_VALIDATOR,
                                 "validationLevel": "strict",
                                 "validationAction": "error"},
    "treatment_events": {"validator": TREATMENT_VALIDATOR,
                         "validationLevel": "strict",
                         "validationAction": "error"},
}

# Reference risk-level list kept beside the validators for the UI legend.
ALLOWED_RISK_LEVELS = RISK_LEVELS


def apply_validators(db: Database) -> list[str]:
    """Create/modify each validated collection so its validator is active.

    Idempotent: uses `collMod` when the collection exists, otherwise `create`.
    Returns the list of collections whose validator was (re)applied.
    """
    applied: list[str] = []
    existing = set(db.list_collection_names())
    for name, opts in VALIDATORS.items():
        cmd = {
            "validator": opts["validator"],
            "validationLevel": opts["validationLevel"],
            "validationAction": opts["validationAction"],
        }
        if name in existing:
            db.command({"collMod": name, **cmd})
        else:
            db.create_collection(name, **cmd)
        applied.append(name)
    return applied


def get_validator_info(db: Database, name: str) -> dict:
    """Return the live validator + action/level for a collection from Atlas."""
    for coll in db.list_collections(filter={"name": name}):
        opts = coll.get("options", {})
        return {
            "validator": opts.get("validator"),
            "validationLevel": opts.get("validationLevel"),
            "validationAction": opts.get("validationAction"),
        }
    return {}


def has_validator(db: Database, name: str) -> bool:
    return bool(get_validator_info(db, name).get("validator"))
