"""Read helpers for the CropTrace demo.

Two contrasting access patterns for the aggregation route:

* `residue_decision_pipeline` — a cross-collection decision query that joins
  normalized `treatment_events` to authoritative `crop_protection_products`
  and the plot's `residue_predictions` via `$lookup`. Use when relationships
  must be resolved against a single source of truth.
* `document_local_view` — the same plot rendered from the embedded `plots`
  document (data read together, no join). Neither is universally faster; each
  fits a different access pattern.

All ids passed in must come from the allowlists in lib.atlas_client, so no
free-form user input ever reaches the query layer.
"""

from __future__ import annotations

import time

from pymongo.database import Database

from lib.atlas_client import PLOT_IDS

VECTOR_INDEX = "croptrace_knowledge_vector_index"

# Indexes the aggregation route relies on (created in seed_data.py).
RELEVANT_INDEXES = [
    "treatment_events: {plot_id: 1, status: 1}",
    "crop_protection_products: {product_id: 1} (unique)",
    "residue_predictions: {plot_id: 1}",
]


def _safe_plot(plot_id: str) -> str:
    """Reject anything not on the allowlist before it reaches a query."""
    if plot_id not in PLOT_IDS:
        raise ValueError(f"plot_id '{plot_id}' is not an allowed demo id")
    return plot_id


def residue_decision_pipeline(plot_id: str) -> list[dict]:
    """Planned treatments for a plot, joined to current product guidance and
    the plot's residue prediction. This is the pipeline shown in the UI."""
    _safe_plot(plot_id)
    return [
        {"$match": {"plot_id": plot_id, "status": "planned"}},
        {"$lookup": {
            "from": "crop_protection_products",
            "localField": "product_ref",
            "foreignField": "product_id",
            "as": "product",
        }},
        {"$unwind": "$product"},
        {"$lookup": {
            "from": "residue_predictions",
            "localField": "plot_id",
            "foreignField": "plot_id",
            "as": "prediction",
        }},
        {"$unwind": "$prediction"},
        {"$project": {
            "_id": 0,
            "treatment_id": 1,
            "planned_dose_l_per_ha": "$dose_l_per_ha",
            "product": "$product.label_name",
            "current_status": "$product.status",
            "current_guidance": "$product.restriction_guidance",
            "phi_days": "$product.phi_days",
            "risk_level": "$prediction.risk_level",
            "predicted_residue_mg_kg": "$prediction.predicted_residue_mg_kg",
            "mrl_mg_kg": "$prediction.mrl_mg_kg",
            "harvest_date": "$prediction.harvest_date",
        }},
        {"$sort": {"predicted_residue_mg_kg": -1}},
    ]


def run_aggregation(db: Database, plot_id: str) -> dict:
    """Run the decision pipeline and time it. Returns rows + elapsed_ms."""
    pipeline = residue_decision_pipeline(plot_id)
    start = time.perf_counter()
    rows = list(db.treatment_events.aggregate(pipeline))
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    for r in rows:
        if r.get("harvest_date"):
            r["harvest_date"] = r["harvest_date"].strftime("%Y-%m-%d")
    return {"pipeline": pipeline, "rows": rows, "elapsed_ms": elapsed_ms,
            "indexes": RELEVANT_INDEXES}


def document_local_view(db: Database, plot_id: str) -> dict:
    """Read the same plot from the embedded `plots` document (no join)."""
    _safe_plot(plot_id)
    start = time.perf_counter()
    plot = db.plots.find_one(
        {"plot_id": plot_id},
        {"_id": 0, "plot_id": 1, "crop": 1, "region": 1,
         "treatments": 1, "residue_prediction": 1})
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    return {"plot": plot, "elapsed_ms": elapsed_ms}


def explain_pipeline(db: Database, plot_id: str) -> dict:
    """Guarded explain for the decision pipeline — allowlisted plots only."""
    pipeline = residue_decision_pipeline(plot_id)
    result = db.command({
        "explain": {"aggregate": "treatment_events", "pipeline": pipeline,
                    "cursor": {}},
        "verbosity": "queryPlanner",
    })
    return result


def list_plots(db: Database) -> list[dict]:
    """Allowlisted plot summaries for the selectors on every route."""
    return list(db.plots.find(
        {"plot_id": {"$in": PLOT_IDS}},
        {"_id": 0, "plot_id": 1, "grower_id": 1, "crop": 1, "region": 1})
        .sort("plot_id", 1))
