"""Demo-readiness checks used by the Demo Readiness page and the smoke tests.

Each check returns a small dict: {name, ok, detail, fix}. Nothing here ever
reveals a secret value — API-key checks report only presence/absence.
"""

from __future__ import annotations

import os

from lib.atlas_client import (COLLECTIONS, PRODUCTS_COLLECTION, db_name,
                              get_client, get_db, products,
                              products_have_embeddings)
from lib.embeddings import embedding_dim, provider_name
from lib.search import TEXT_INDEX, VECTOR_INDEX

REQUIRED_BTREE = {
    PRODUCTS_COLLECTION: ["product_id_1", "product_type_1_category_1_status_1"],
}


def _row(name: str, ok: bool, detail: str, fix: str = "") -> dict:
    return {"name": name, "ok": ok, "detail": detail, "fix": fix}


def check_connectivity() -> dict:
    try:
        get_client().admin.command("ping")
        return _row("MongoDB connectivity", True, f"Connected · db `{db_name()}`")
    except Exception as e:  # noqa: BLE001
        return _row("MongoDB connectivity", False, str(e),
                    "Set MONGODB_URI in .env (an existing Atlas cluster).")


def check_seed() -> dict:
    db = get_db()
    counts = {c: db[c].count_documents({}) for c in COLLECTIONS}
    seeded = counts.get(PRODUCTS_COLLECTION, 0) > 0
    detail = ", ".join(f"{c}={n}" for c, n in counts.items())
    return _row("Seeded catalog", seeded, detail,
                "" if seeded else "Run `python3 seed_data.py`.")


def check_btree_indexes() -> dict:
    db = get_db()
    missing = []
    for coll, wanted in REQUIRED_BTREE.items():
        names = set(db[coll].index_information().keys())
        missing += [f"{coll}.{i}" for i in wanted if i not in names]
    ok = not missing
    return _row("Required indexes", ok,
                "Present" if ok else f"Missing: {missing}",
                "" if ok else "Re-run `python3 seed_data.py`.")


def _search_index(name: str, label: str) -> dict:
    try:
        indexes = {ix["name"]: ix for ix in products().list_search_indexes()}
    except Exception as e:  # noqa: BLE001
        return _row(label, False, str(e),
                    "Run `python3 scripts/create_indexes.py`.")
    ix = indexes.get(name)
    if not ix:
        return _row(label, False, "Not created",
                    "Run `python3 scripts/create_indexes.py`.")
    queryable = ix.get("queryable", False)
    return _row(label, queryable,
                "READY" if queryable else ix.get("status", "BUILDING"),
                "" if queryable else "Wait ~1-2 min for Atlas to build it.")


def check_text_index() -> dict:
    return _search_index(TEXT_INDEX, "Atlas Search index (keyword mode)")


def check_vector_index() -> dict:
    return _search_index(VECTOR_INDEX, "Vector Search index (semantic mode)")


def check_embeddings() -> dict:
    ok = products_have_embeddings()
    detail = (f"provider `{provider_name()}` · {embedding_dim()} dims"
              if ok else "No product carries an embedding")
    return _row("Product embeddings", ok, detail,
                "" if ok else "Re-run `python3 seed_data.py`.")


def check_ai_keys() -> dict:
    voyage = bool(os.getenv("VOYAGE_API_KEY"))
    anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
    detail = (f"VOYAGE_API_KEY={'set' if voyage else 'absent'} · "
              f"ANTHROPIC_API_KEY={'set' if anthropic else 'absent'}")
    # Optional by design — every search mode runs without keys.
    return _row("Optional AI keys", True, detail,
                "Keys are optional — the local embedder and the extractive "
                "summary need none.")


def run_all() -> list[dict]:
    return [check_connectivity(), check_seed(), check_btree_indexes(),
            check_text_index(), check_vector_index(), check_embeddings(),
            check_ai_keys()]
