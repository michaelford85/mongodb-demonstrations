"""Synthetic data builders for the Field Advisor demo.

Everything here is fictional. Grower names, farm names, and product names are
invented for the demo and correspond to no real person, farm, company, or
brand. Deterministic seeding keeps demos and screenshots reproducible.
"""

import random
import uuid
from datetime import datetime, timedelta, timezone

from lib.atlas_client import (CROPS, PRODUCT_LINES, REGIONS, SEASONS,
                              SEVERITIES)
from lib.knowledge import ARTICLES

random.seed(7)

FIRST_NAMES = ["Ava", "Liam", "Noah", "Mia", "Elena", "Marcus", "Priya",
               "Diego", "Sofia", "Kenji", "Amara", "Lucas", "Nora", "Theo"]
LAST_NAMES = ["Reyes", "Okafor", "Nguyen", "Silva", "Novak", "Haddad",
              "Lindqvist", "Costa", "Ibrahim", "Tanaka", "Moreau", "Park"]
FARM_ADJ = ["Prairie", "Cedar", "Willow", "Sunrise", "Twin Oaks", "Clearwater",
            "Rolling Hills", "Meadowbrook", "Ironwood", "Harvest Moon"]
FARM_NOUN = ["Farms", "Acres", "Ranch", "Fields", "Growers", "Ag Co-op"]

# Invented product catalog — generic agronomy product lines, no real brands.
PRODUCT_CATALOG = [
    ("GuardCoat Seed Shield", "Seed Treatment",
     "Fungicide + insecticide seed coating for early-season protection."),
    ("VeriShield Fungicide", "Fungicide",
     "Broad-spectrum foliar fungicide for cereal and row-crop diseases."),
    ("ClearRow Herbicide", "Herbicide",
     "Residual + post-emergence herbicide for tough broadleaf weeds."),
    ("StalkGuard Insecticide", "Insecticide",
     "Contact + systemic insecticide for chewing and sucking pests."),
    ("RootBiotic Inoculant", "Biologicals",
     "Rhizobium inoculant that boosts nodulation and nitrogen fixation."),
    ("FieldLens Insights", "Digital Agronomy",
     "Imagery + agronomy platform for scouting and variable-rate maps."),
]

CASE_SUMMARIES = [
    "Grower reports yellowing on lower leaves after heavy rain.",
    "Patchy stand loss showing up in a low, wet corner of the field.",
    "Orange pustules found on upper leaves during routine scouting.",
    "Post-emergence weed escapes surviving the last herbicide pass.",
    "Lodged plants and goosenecking after a wind event.",
    "Small larvae found on flowering plants near the field edge.",
    "Poor nodulation suspected — plants pale and stunted at V3.",
    "Uneven dry-down and green stem slowing harvest planning.",
]

NEXT_ACTIONS = [
    "Pull a tissue test before recommending any nutrient application.",
    "Schedule a field visit to confirm the diagnosis on the ground.",
    "Recommend an overlapping residual on the next pass.",
    "Prioritize scouting the stressed zones flagged on imagery.",
    "Confirm crop staging against the label pre-harvest interval.",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def build_growers(n: int = 24) -> list[dict]:
    growers = []
    for i in range(1, n + 1):
        region = random.choice(REGIONS)
        adj, noun = random.choice(FARM_ADJ), random.choice(FARM_NOUN)
        growers.append({
            "grower_id": f"GRW-{1000 + i}",
            "name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
            "farm_name": f"{adj} {noun}",
            "region": region,
            "primary_crops": random.sample(CROPS, k=random.randint(1, 3)),
            "tier": random.choices(["standard", "preferred", "key_account"],
                                   weights=[60, 30, 10])[0],
            "total_acres": random.choice([320, 640, 1200, 2400, 4800]),
            "created_at": _now() - timedelta(days=random.randint(60, 1500)),
        })
    return growers


def build_fields(growers: list[dict]) -> list[dict]:
    """Each grower manages 1-3 fields spanning their primary crops."""
    fields = []
    for g in growers:
        for _ in range(random.randint(1, 3)):
            crop = random.choice(g["primary_crops"])
            fields.append({
                "field_id": _id("FLD"),
                "grower_id": g["grower_id"],
                "name": f"{random.choice(FARM_ADJ)} {random.randint(1, 40)}",
                "crop": crop,
                "region": g["region"],
                "acreage": random.choice([40, 80, 120, 160, 240, 320]),
                "soil_type": random.choice(["silt loam", "clay loam", "sandy loam",
                                            "loam", "silty clay"]),
                "season": random.choice(SEASONS),
                "planting_date": _now() - timedelta(days=random.randint(5, 120)),
            })
    return fields


def build_products() -> list[dict]:
    products = []
    for i, (name, line, desc) in enumerate(PRODUCT_CATALOG, 1):
        products.append({
            "product_id": f"PRD-{300 + i}",
            "name": name,
            "product_line": line,
            "description": desc,
            "target_crops": random.sample(CROPS, k=random.randint(2, 4)),
        })
    return products


def _interaction(author: str, kind: str, text: str, when: datetime) -> dict:
    return {"interaction_id": _id("INT"), "type": kind, "author": author,
            "text": text, "created_at": when}


def build_support_cases(growers: list[dict], fields: list[dict],
                        products: list[dict]) -> tuple[list[dict], list[dict]]:
    """Build support cases plus their standalone interaction_history rows.

    Each case embeds a short interactions array (fast to render), and every
    interaction is *also* written to interaction_history so the demo can show
    both an embedded view and an independent audit collection in Atlas.
    """
    fields_by_grower: dict[str, list[dict]] = {}
    for f in fields:
        fields_by_grower.setdefault(f["grower_id"], []).append(f)

    cases, history = [], []
    for i, g in enumerate(growers, 1):
        # Not every grower has an open case — keeps the data realistic.
        for _ in range(random.randint(0, 2)):
            gfields = fields_by_grower.get(g["grower_id"], [])
            fld = random.choice(gfields) if gfields else None
            crop = fld["crop"] if fld else random.choice(CROPS)
            product = random.choice(products)
            opened = _now() - timedelta(days=random.randint(0, 40),
                                        hours=random.randint(0, 23))
            case_id = f"CASE-{5000 + len(cases) + 1}"

            interactions = [
                _interaction("Field Rep", "note",
                             random.choice(CASE_SUMMARIES), opened),
            ]
            if random.random() > 0.4:
                interactions.append(_interaction(
                    "Agronomist", "recommendation",
                    "Suggested " + product["name"] + ". "
                    + random.choice(NEXT_ACTIONS),
                    opened + timedelta(hours=random.randint(2, 30))))

            case = {
                "case_id": case_id,
                "grower_id": g["grower_id"],
                "field_id": fld["field_id"] if fld else None,
                "crop": crop,
                "region": g["region"],
                "season": fld["season"] if fld else random.choice(SEASONS),
                "product_line": product["product_line"],
                "severity": random.choice(SEVERITIES),
                "status": random.choices(["open", "in_progress", "resolved"],
                                         weights=[45, 30, 25])[0],
                "summary": interactions[0]["text"],
                "recommended_action": random.choice(NEXT_ACTIONS),
                "opened_at": opened,
                "updated_at": interactions[-1]["created_at"],
                "interactions": interactions,
            }
            cases.append(case)
            for it in interactions:
                history.append({**it, "case_id": case_id,
                                "grower_id": g["grower_id"]})
    return cases, history


def build_knowledge_articles() -> list[dict]:
    """Materialize the knowledge corpus with stable article ids."""
    articles = []
    for i, art in enumerate(ARTICLES, 1):
        articles.append({"article_id": f"KA-{700 + i}",
                         "created_at": _now(), **art})
    return articles
