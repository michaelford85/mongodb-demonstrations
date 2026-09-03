"""Demo-readiness checks used by the Demo Readiness page and the smoke tests.

Each check returns a small dict: {name, ok, detail, fix}. Nothing here ever
reveals a secret value — API-key checks report only presence/absence.
"""

from __future__ import annotations

import os

from lib.atlas_client import (COLLECTIONS, KNOWLEDGE_COLLECTION,
                              VALIDATED_COLLECTIONS, db_name, get_client,
                              get_db, knowledge_has_embeddings)
from lib.queries import VECTOR_INDEX
from lib.schema import has_validator

REQUIRED_BTREE = {
    "crop_protection_products": "product_id_1",
    "treatment_events": "plot_id_1_status_1",
    "residue_predictions": "plot_id_1",
}


def _row(name: str, ok: bool, detail: str, fix: str = "") -> dict:
    return {"name": name, "ok": ok, "detail": detail, "fix": fix}


def check_connectivity() -> dict:
    try:
        get_client().admin.command("ping")
        return _row("MongoDB connectivity", True, f"Connected · db `{db_name()}`")
    except Exception as e:  # noqa: BLE001
        return _row("MongoDB connectivity", False, str(e),
                    "Set MONGODB_URI in .env (atlas-cluster-provisioning cluster).")


def check_seed() -> dict:
    db = get_db()
    counts = {c: db[c].count_documents({}) for c in COLLECTIONS}
    seeded = counts.get("plots", 0) > 0
    detail = ", ".join(f"{c}={n}" for c, n in counts.items())
    return _row("Seeded data", seeded, detail,
                "" if seeded else "Run `python3 seed_data.py`.")


def check_validators() -> dict:
    db = get_db()
    missing = [c for c in VALIDATED_COLLECTIONS if not has_validator(db, c)]
    ok = not missing
    return _row("Collection validators", ok,
                "All validators active" if ok else f"Missing: {missing}",
                "" if ok else "Re-run `python3 seed_data.py`.")


def check_btree_indexes() -> dict:
    db = get_db()
    missing = []
    for coll, idx in REQUIRED_BTREE.items():
        names = set(db[coll].index_information().keys())
        if idx not in names:
            missing.append(f"{coll}.{idx}")
    ok = not missing
    return _row("Required indexes", ok,
                "Present" if ok else f"Missing: {missing}",
                "" if ok else "Re-run `python3 seed_data.py`.")


def check_vector_index() -> dict:
    coll = get_db()[KNOWLEDGE_COLLECTION]
    try:
        indexes = {ix["name"]: ix for ix in coll.list_search_indexes()}
    except Exception as e:  # noqa: BLE001
        return _row("Vector Search index", False, str(e),
                    "Run `python3 scripts/create_indexes.py`.")
    ix = indexes.get(VECTOR_INDEX)
    if not ix:
        return _row("Vector Search index", False, "Not created",
                    "Run `python3 scripts/create_indexes.py`.")
    queryable = ix.get("queryable", False)
    return _row("Vector Search index", queryable,
                "READY" if queryable else ix.get("status", "BUILDING"),
                "" if queryable else "Wait ~1-2 min for Atlas to build it.")


def check_embeddings() -> dict:
    ok = knowledge_has_embeddings()
    return _row("Knowledge embeddings", ok,
                "Present" if ok else "None", "" if ok else "Re-run seed.")


def check_ai_keys() -> dict:
    voyage = bool(os.getenv("VOYAGE_API_KEY"))
    anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
    detail = (f"VOYAGE_API_KEY={'set' if voyage else 'absent'} · "
              f"ANTHROPIC_API_KEY={'set' if anthropic else 'absent'}")
    # Optional by design — always 'ok', the assistant runs without keys.
    return _row("Optional AI keys", True, detail,
                "Keys are optional — the no-keys mode still runs retrieval.")


def run_all() -> list[dict]:
    return [check_connectivity(), check_seed(), check_validators(),
            check_btree_indexes(), check_vector_index(), check_embeddings(),
            check_ai_keys()]
