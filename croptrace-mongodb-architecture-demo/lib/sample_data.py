"""Synthetic data builders for the CropTrace demo.

Everything here is fictional and deterministic (fixed seed) so demos and
screenshots are reproducible. Grower, plot, and product names are invented and
correspond to no real person, farm, company, or brand.

Two shapes on purpose:
* `plots` embed the treatment/weather/prediction data that is *read together*
  for a single plot view (document locality).
* `crop_protection_products` is the authoritative master-data collection, and
  `treatment_events` / `residue_predictions` are normalized so the aggregation
  and `$lookup` route has real cross-collection relationships to resolve.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from lib.atlas_client import (CROPS, GROWER_IDS, PLOT_IDS, PRODUCT_CATEGORIES,
                              PRODUCT_IDS, REGIONS, RISK_LEVELS)

random.seed(11)

_BASE = datetime(2025, 5, 1, tzinfo=timezone.utc)

VARIETIES = {
    "Apple": ["Gala", "Braeburn"], "Grape": ["Chardonnay", "Merlot"],
    "Strawberry": ["Elsanta", "Clery"], "Tomato": ["Roma", "San Marzano"],
    "Lettuce": ["Batavia", "Romaine"], "Potato": ["Charlotte", "Agria"],
}

PRODUCT_NAMES = [
    ("CardaFol SC", "Fungicide"), ("VineGuard WP", "Fungicide"),
    ("AphidStop EC", "Insecticide"), ("MiteClear SC", "Insecticide"),
    ("CleanRow WG", "Herbicide"), ("EdgeControl SL", "Herbicide"),
    ("BioShield WP", "Biocontrol"), ("TrichoDefend WG", "Biocontrol"),
]

RESTRICTION_TEXT = {
    "active": "Approved for use per current label.",
    "restricted": "Use restricted near harvest — observe extended PHI.",
    "withdrawn": "Authorisation withdrawn — do not apply.",
}


def build_crops() -> list[dict]:
    return [{"crop": c, "varieties": VARIETIES[c],
             "residue_sensitivity": RISK_LEVELS[i % len(RISK_LEVELS)]}
            for i, c in enumerate(CROPS)]


def build_products() -> list[dict]:
    """Authoritative crop-protection-product master data (frequently updated)."""
    products = []
    for i, pid in enumerate(PRODUCT_IDS):
        name, category = PRODUCT_NAMES[i]
        status = "active" if i % 4 else "restricted"
        products.append({
            "product_id": pid,
            "label_name": name,
            "category": category,
            "status": status,
            "reentry_interval_hours": 12 + 6 * (i % 4),
            "phi_days": 3 + (i % 5),
            "restriction_guidance": RESTRICTION_TEXT[status],
            "version": 1,
            "updated_at": _BASE,
        })
    return products


def _weather(n: int) -> list[dict]:
    obs = []
    for d in range(n):
        obs.append({
            "observed_at": _BASE + timedelta(days=d * 3),
            "temp_c": round(16 + random.uniform(-4, 10), 1),
            "rain_mm": round(max(0.0, random.uniform(-2, 12)), 1),
            "humidity_pct": random.randint(45, 90),
        })
    return obs


def _prediction(level: str) -> dict:
    return {
        "risk_level": level,
        "predicted_residue_mg_kg": round(0.1 + RISK_LEVELS.index(level) * 0.35
                                          + random.uniform(0, 0.15), 3),
        "mrl_mg_kg": 0.9,
        "harvest_date": _BASE + timedelta(days=random.randint(20, 60)),
        "model_version": "croptrace-risk-0.4",
        "generated_at": _BASE + timedelta(days=1),
    }


def build_plots_and_events(products: list[dict]) -> tuple[list, list, list]:
    """Build plots (embedded) plus normalized treatment/prediction collections."""
    plots, events, predictions = [], [], []
    for i, plot_id in enumerate(PLOT_IDS):
        crop = CROPS[i % len(CROPS)]
        grower = GROWER_IDS[i % len(GROWER_IDS)]
        region = REGIONS[i % len(REGIONS)]
        level = RISK_LEVELS[i % len(RISK_LEVELS)]
        n_treat = 2 + (i % 2)
        embedded_treatments = []
        for t in range(n_treat):
            prod = products[(i + t) % len(products)]
            tid = f"TRT-{i + 1:03d}-{t + 1}"
            snapshot = {  # historical: captured at application time
                "label_name": prod["label_name"],
                "category": prod["category"],
                "captured_at": _BASE + timedelta(days=t * 5),
                "snapshot_version": prod["version"],
            }
            event = {
                "treatment_id": tid, "plot_id": plot_id,
                "product_ref": prod["product_id"],
                "status": "applied" if t < n_treat - 1 else "planned",
                "applied_at": _BASE + timedelta(days=t * 5),
                "dose_l_per_ha": round(0.5 + 0.4 * t, 2),
                "product_snapshot": snapshot,
            }
            events.append(event)
            embedded_treatments.append({k: event[k] for k in (
                "treatment_id", "product_ref", "status", "applied_at",
                "dose_l_per_ha", "product_snapshot")})
        prediction = _prediction(level)
        predictions.append({**prediction, "prediction_id": f"PRD-{i + 1:03d}",
                            "plot_id": plot_id})
        plots.append({
            "plot_id": plot_id, "grower_id": grower, "crop": crop,
            "variety": VARIETIES[crop][i % 2], "region": region,
            "area_hectares": round(1.5 + i * 0.4, 1),
            "treatments": embedded_treatments,
            "weather_observations": _weather(3),
            "residue_prediction": prediction,
        })
    return plots, events, predictions
