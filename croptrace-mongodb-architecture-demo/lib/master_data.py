"""Master-data helpers: controlled duplication vs authoritative reference.

Each treatment carries a small `product_snapshot` (a display/history record of
what the product looked like *when it was applied*) plus a `product_ref` to the
authoritative `crop_protection_products` document. Changing the authoritative
record updates the resolved view everywhere, while the historical snapshot on
past treatments deliberately does not move. This is a design decision, not a
claim of automatic referential integrity.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pymongo.database import Database

from lib.atlas_client import PRODUCT_IDS

# Fields intentionally frozen as a historical snapshot on each treatment.
SNAPSHOT_FIELDS = ["label_name", "category", "snapshot_version"]
# Fields deliberately resolved live from the authoritative product record.
RESOLVED_FIELDS = ["status", "restriction_guidance", "phi_days",
                   "reentry_interval_hours", "version"]


def _safe_product(product_id: str) -> str:
    if product_id not in PRODUCT_IDS:
        raise ValueError(f"product_id '{product_id}' is not an allowed demo id")
    return product_id


def get_product(db: Database, product_id: str) -> dict | None:
    _safe_product(product_id)
    return db.crop_protection_products.find_one(
        {"product_id": product_id}, {"_id": 0})


def update_product_guidance(db: Database, product_id: str, *,
                            status: str, restriction_guidance: str) -> dict:
    """Change an authoritative product's status/guidance and bump its version.

    Only the master record changes; existing treatment snapshots are untouched.
    """
    _safe_product(product_id)
    result = db.crop_protection_products.find_one_and_update(
        {"product_id": product_id},
        {"$set": {"status": status,
                  "restriction_guidance": restriction_guidance,
                  "updated_at": datetime.now(timezone.utc)},
         "$inc": {"version": 1}},
        projection={"_id": 0},
        return_document=True,
    )
    return result


def resolve_treatments_for_product(db: Database, product_id: str) -> list[dict]:
    """For every treatment referencing this product, contrast the frozen
    snapshot with the freshly-resolved authoritative fields."""
    _safe_product(product_id)
    product = get_product(db, product_id) or {}
    rows = []
    for ev in db.treatment_events.find(
            {"product_ref": product_id},
            {"_id": 0, "treatment_id": 1, "plot_id": 1, "product_snapshot": 1}):
        snap = ev.get("product_snapshot", {}) or {}
        rows.append({
            "treatment_id": ev["treatment_id"],
            "plot_id": ev["plot_id"],
            "snapshot": {k: snap.get(k) for k in SNAPSHOT_FIELDS},
            "resolved": {k: product.get(k) for k in RESOLVED_FIELDS},
        })
    return rows


def snapshot_vs_reference_note() -> dict:
    """Static design-decision copy for the UI panel."""
    return {
        "snapshot_fields": SNAPSHOT_FIELDS,
        "resolved_fields": RESOLVED_FIELDS,
        "why": ("Product labels and restriction guidance change often, so they "
                "are resolved from the single authoritative record rather than "
                "copied into every treatment. A tiny snapshot is kept only for "
                "display/history of what was true at application time."),
    }
