"""Synthetic catalog for Product Catalog Studio.

Everything here is fictional. Kestrel Labworks, every product name, SKU, price,
and specification is invented for this demonstration and corresponds to no real
company, brand, or product. Deterministic generation keeps demos and
screenshots reproducible.

Three product types deliberately carry *different* attributes — that variation
is the document-modelling point of the demo:

    equipment     -> specs{}, lead_time_days, stock{}
    consumable    -> pack{}, handling{}, stock{}
    service_plan  -> coverage{}, term{}, entitlements[]
"""

import random
from datetime import datetime, timedelta, timezone

random.seed(11)

# (name, category, summary, description, tags, price, type-specific fields)
EQUIPMENT = [
    ("Kestrel Vortex V2 Sample Mixer", "Sample Preparation",
     "Benchtop vortex mixer for small-batch sample homogenisation.",
     "Compact benchtop mixer with a variable 300–3000 rpm range and swappable "
     "tube heads. Intended for routine sample preparation on a crowded bench.",
     ["mixer", "benchtop", "sample prep", "quiet"], 1450.00,
     {"specs": {"power_source": "Mains 120V", "weight_kg": 4.2,
                "noise_db": 48, "warranty_months": 24},
      "lead_time_days": 10}),
    ("Kestrel Cryoline CF-8 Chiller", "Environmental Control",
     "Recirculating chiller that holds a bath to ±0.1 °C.",
     "Recirculating chiller for temperature-sensitive workflows. Holds a bath "
     "within ±0.1 °C and reports setpoint drift over a serial link.",
     ["chiller", "cooling", "temperature stability"], 8900.00,
     {"specs": {"power_source": "Mains 230V", "weight_kg": 31.0,
                "noise_db": 55, "warranty_months": 36},
      "lead_time_days": 28}),
    ("Kestrel Lumina Q Spectrophotometer", "Measurement",
     "Dual-beam spectrophotometer for absorbance assays.",
     "Dual-beam optical bench covering 190–1100 nm with a stray-light trap and "
     "onboard method storage for repeat absorbance assays.",
     ["spectrophotometer", "absorbance", "optics"], 15750.00,
     {"specs": {"power_source": "Mains 120V", "weight_kg": 18.5,
                "noise_db": 42, "warranty_months": 24},
      "lead_time_days": 21}),
    ("Kestrel Fieldmate P1 Portable Balance", "Measurement",
     "Battery-powered balance for weighing away from the bench.",
     "Battery-powered precision balance with a draft collar and a rugged case, "
     "built for weighing samples away from mains power.",
     ["balance", "portable", "battery", "field work"], 2300.00,
     {"specs": {"power_source": "Battery", "weight_kg": 2.1,
                "noise_db": 0, "warranty_months": 12},
      "lead_time_days": 5}),
    ("Kestrel Aeroflow AF-40 Pneumatic Press", "Sample Preparation",
     "Pneumatic pellet press for solid-sample discs.",
     "Air-driven press that produces uniform pellets for solid-sample "
     "measurement, with a guarded die stage and a repeatable dwell timer.",
     ["press", "pellet", "pneumatic", "solids"], 6400.00,
     {"specs": {"power_source": "Pneumatic", "weight_kg": 44.0,
                "noise_db": 68, "warranty_months": 24},
      "lead_time_days": 35}),
    ("Kestrel Stillroom SR-2 Fume Enclosure", "Environmental Control",
     "Ductless enclosure for low-volume solvent handling.",
     "Ductless filtered enclosure for low-volume solvent handling where no duct "
     "run exists. Filter saturation is reported on the front panel.",
     ["enclosure", "ductless", "solvent", "ventilation"], 5200.00,
     {"specs": {"power_source": "Mains 230V", "weight_kg": 58.0,
                "noise_db": 52, "warranty_months": 24},
      "lead_time_days": 42}),
]

CONSUMABLE = [
    ("Kestrel ClearPath Buffer Concentrate", "Reagents",
     "10x buffer concentrate for routine dilution series.",
     "Ten-times buffer concentrate supplied in shatter-resistant bottles for "
     "routine dilution series. Lot certificates ship with every case.",
     ["buffer", "reagent", "concentrate"], 68.00,
     {"pack": {"units_per_pack": 6, "unit_size": "1 L"},
      "handling": {"hazard_class": "Irritant", "shelf_life_months": 18,
                   "storage": "2–8 °C"}}),
    ("Kestrel Aliquot Microtube Rack Pack", "Labware",
     "Pre-racked microtubes for aliquoting and archiving.",
     "Pre-racked 2 mL microtubes with writable caps, supplied in sealed sleeves "
     "so a rack can be opened without exposing the rest of the case.",
     ["microtube", "labware", "aliquot", "racked"], 142.00,
     {"pack": {"units_per_pack": 500, "unit_size": "2 mL"},
      "handling": {"hazard_class": "None", "shelf_life_months": 60,
                   "storage": "Ambient"}}),
    ("Kestrel Fineline 0.22 µm Syringe Filters", "Filtration",
     "Sterile 0.22 µm syringe filters for sample clarification.",
     "Individually wrapped sterile syringe filters with a low-binding membrane, "
     "used to clarify samples immediately before measurement.",
     ["filter", "sterile", "0.22 micron", "clarification"], 210.00,
     {"pack": {"units_per_pack": 100, "unit_size": "0.22 µm"},
      "handling": {"hazard_class": "None", "shelf_life_months": 36,
                   "storage": "Ambient"}}),
    ("Kestrel Solvex Rinse Solvent", "Reagents",
     "High-purity rinse solvent for optical surfaces.",
     "High-purity rinse solvent for cleaning optical windows and flow cells. "
     "Flammable; ships in a vented secondary container.",
     ["solvent", "rinse", "flammable", "cleaning"], 96.00,
     {"pack": {"units_per_pack": 4, "unit_size": "2.5 L"},
      "handling": {"hazard_class": "Flammable", "shelf_life_months": 24,
                   "storage": "Flammables cabinet"}}),
    ("Kestrel Etchant Descaling Concentrate", "Reagents",
     "Corrosive descaler for chiller and bath loops.",
     "Corrosive descaling concentrate for recirculating loops and baths. "
     "Requires acid-resistant gloves and an eyewash within reach.",
     ["descaler", "corrosive", "maintenance", "chiller"], 121.00,
     {"pack": {"units_per_pack": 2, "unit_size": "5 L"},
      "handling": {"hazard_class": "Corrosive", "shelf_life_months": 12,
                   "storage": "Corrosives cabinet"}}),
    ("Kestrel Gridline Filter Membranes", "Filtration",
     "Gridded membranes for particulate counting workflows.",
     "Gridded cellulose membranes in a dispenser pack, used for particulate "
     "counting where the grid keeps a manual count traceable.",
     ["membrane", "gridded", "particulate", "counting"], 178.00,
     {"pack": {"units_per_pack": 200, "unit_size": "47 mm"},
      "handling": {"hazard_class": "None", "shelf_life_months": 48,
                   "storage": "Ambient"}}),
]

SERVICE_PLAN = [
    ("Kestrel Uptime Essentials", "Support",
     "Remote-first support plan with a next-business-day target.",
     "Remote diagnostics and parts dispatch with a next-business-day response "
     "target. Suited to instruments that are not on a critical path.",
     ["support", "remote", "next business day"], 1200.00,
     {"coverage": {"response_tier": "Next business day", "on_site": False,
                   "hours": "Business hours"},
      "term": {"months": 12, "auto_renew": True},
      "entitlements": ["Remote diagnostics", "Parts dispatch",
                       "Firmware updates"]}),
    ("Kestrel Uptime Priority", "Support",
     "Same-day on-site support for bench-critical instruments.",
     "Same-day on-site attendance with a loaner option, for instruments where a "
     "day of downtime stops the workflow.",
     ["support", "on-site", "same day", "loaner"], 4800.00,
     {"coverage": {"response_tier": "Same day", "on_site": True,
                   "hours": "Extended"},
      "term": {"months": 12, "auto_renew": True},
      "entitlements": ["On-site attendance", "Loaner instrument",
                       "Remote diagnostics", "Parts dispatch"]}),
    ("Kestrel Uptime Critical", "Support",
     "Four-hour response cover for continuously running instruments.",
     "Four-hour response window with 24/7 coverage and a named engineer, for "
     "instruments that run continuously.",
     ["support", "4-hour", "24/7", "critical"], 11500.00,
     {"coverage": {"response_tier": "4-hour", "on_site": True,
                   "hours": "24/7"},
      "term": {"months": 24, "auto_renew": False},
      "entitlements": ["On-site attendance", "Named engineer",
                       "Loaner instrument", "Quarterly health report"]}),
    ("Kestrel Calibration Annual", "Calibration",
     "Scheduled annual calibration with certificates.",
     "One scheduled calibration visit per year with as-found and as-left "
     "certificates, plus a reminder before the due date.",
     ["calibration", "certificate", "annual", "scheduled"], 950.00,
     {"coverage": {"response_tier": "Next business day", "on_site": True,
                   "hours": "Business hours"},
      "term": {"months": 12, "auto_renew": True},
      "entitlements": ["Annual calibration visit", "As-found/as-left records",
                       "Due-date reminders"]}),
    ("Kestrel Calibration Quarterly", "Calibration",
     "Quarterly calibration for tightly controlled methods.",
     "Four calibration visits per year with interim verification checks, for "
     "methods that must hold a tight tolerance between visits.",
     ["calibration", "quarterly", "verification"], 3100.00,
     {"coverage": {"response_tier": "Same day", "on_site": True,
                   "hours": "Business hours"},
      "term": {"months": 12, "auto_renew": True},
      "entitlements": ["Four calibration visits", "Interim verification",
                       "Drift trend summary"]}),
    ("Kestrel Method Onboarding", "Training",
     "Remote onboarding sessions for new bench staff.",
     "A set of remote onboarding sessions covering instrument operation and "
     "method setup, with recordings retained for the plan term.",
     ["training", "onboarding", "remote", "methods"], 2400.00,
     {"coverage": {"response_tier": "Remote only", "on_site": False,
                   "hours": "Business hours"},
      "term": {"months": 6, "auto_renew": False},
      "entitlements": ["Four remote sessions", "Session recordings",
                       "Method templates"]}),
]

SOURCES = {"equipment": EQUIPMENT, "consumable": CONSUMABLE,
           "service_plan": SERVICE_PLAN}

SKU_PREFIX = {"equipment": "EQP", "consumable": "CNS", "service_plan": "SVC"}

# Deterministic status mix so the availability filter always has something to
# show for every product type.
STATUS_CYCLE = ["active", "active", "limited", "active", "preorder",
                "discontinued"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stock(product_type: str, index: int) -> dict | None:
    """Physical goods carry stock; a service plan has no stock at all."""
    if product_type == "service_plan":
        return None
    on_hand = [0, 4, 18, 60, 240, 900][index % 6]
    return {"on_hand": on_hand, "reserved": min(on_hand, index * 2),
             "warehouse": ["ORD-1", "ORD-2"][index % 2]}


def build_products() -> list[dict]:
    """Materialize the full fictional catalog as MongoDB documents."""
    docs: list[dict] = []
    for product_type, rows in SOURCES.items():
        for i, (name, category, summary, description, tags, price,
                extra) in enumerate(rows):
            seq = len(docs) + 1
            doc = {
                "product_id": f"PCS-{1000 + seq}",
                "sku": f"{SKU_PREFIX[product_type]}-{100 + i:03d}",
                "name": name,
                "product_type": product_type,
                "category": category,
                "status": STATUS_CYCLE[(seq - 1) % len(STATUS_CYCLE)],
                "summary": summary,
                "description": description,
                "tags": tags,
                "price": {"amount": price, "currency": "USD",
                          "unit": "per plan" if product_type == "service_plan"
                                  else "per pack" if product_type == "consumable"
                                  else "each"},
                "created_at": _now() - timedelta(days=400 - seq * 7),
                "updated_at": _now() - timedelta(days=seq % 30),
                "source": "seed",
            }
            doc.update(extra)
            stock = _stock(product_type, i)
            if stock:
                doc["stock"] = stock
            docs.append(doc)
    return docs
