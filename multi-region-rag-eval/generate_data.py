"""Generate a synthetic routing dataset.

All values are fabricated. No real customer, company, or person names are used.
The generator intentionally varies the per-region attributes to mirror the
different operational rules each regional team applies in production.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from faker import Faker

from config import CASE_REASONS, PRODUCT_GROUPS, REGIONS, SALES_AREAS, load_settings
from embeddings import compose_account_text, embed_documents

OUTPUT_PATH = Path(__file__).parent / "data" / "accounts.jsonl"

_ACCOUNT_PREFIXES = (
    "Aurora", "Helios", "Nimbus", "Orbital", "Quartz", "Vertex", "Zephyr",
    "Solstice", "Halcyon", "Pinnacle", "Cascade", "Meridian", "Lumen", "Borealis",
)
_ACCOUNT_SUFFIXES = (
    "Logistics", "Systems", "Holdings", "Industries", "Partners", "Dynamics",
    "Analytics", "Robotics", "Foods", "Energy", "Mobility", "Networks",
)


def _account_name(rng: random.Random) -> str:
    return (
        f"{rng.choice(_ACCOUNT_PREFIXES)} "
        f"{rng.choice(_ACCOUNT_SUFFIXES)} "
        f"{rng.randint(1000, 9999)}"
    )


def _regional_attrs(region: str, rng: random.Random, fake: Faker) -> dict[str, Any]:
    """Return a region-specific attribute bag to demonstrate schema variability."""
    if region == "France":
        return {
            "tva_number": f"FR{rng.randint(10, 99)}{rng.randint(100000000, 999999999)}",
            "language": "fr-FR",
            "priority_tier": rng.choice(["gold", "silver", "bronze"]),
            "channel_partner": fake.color_name() + " Channel",
        }
    if region == "Italy":
        return {
            "partita_iva": f"IT{rng.randint(10000000000, 99999999999)}",
            "sla_hours": rng.choice([8, 24, 48]),
            "distributor_code": f"DIST-{rng.randint(100, 999)}",
        }
    if region == "Germany":
        return {
            "ust_id": f"DE{rng.randint(100000000, 999999999)}",
            "kostenstelle": f"KS-{rng.randint(1000, 9999)}",
            "eskalationsstufe": rng.choice([1, 2, 3]),
        }
    if region == "Spain":
        return {
            "cif": f"ES{rng.choice('ABCDEFGH')}{rng.randint(10000000, 99999999)}",
            "sla_hours": rng.choice([24, 48, 72]),
            "segment": rng.choice(["enterprise", "mid_market", "smb"]),
        }
    # UK
    return {
        "vat_number": f"GB{rng.randint(100000000, 999999999)}",
        "contract_type": rng.choice(["managed_services", "self_serve", "hybrid"]),
        "sla_hours": rng.choice([4, 8, 24]),
    }


def generate(
    row_count: int,
    embed_dim: int,
    voyage_api_key: str,
    voyage_model: str,
    seed: int = 42,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    fake = Faker()
    Faker.seed(seed)
    rows: list[dict[str, Any]] = []
    for _ in range(row_count):
        region = rng.choice(REGIONS)
        product_group = rng.choice(PRODUCT_GROUPS)
        account_name = _account_name(rng)
        row = {
            "account_name": account_name,
            "product_group": product_group,
            "case_reason": rng.choice(CASE_REASONS),
            "operational_identity": f"OPS-{rng.randint(10000, 99999)}",
            "sales_area": rng.choice(SALES_AREAS),
            "service_agent_id": f"AGT-{rng.randint(1000, 9999)}",
            "region": region,
            "regional_attrs": _regional_attrs(region, rng, fake),
            "embedding_text": compose_account_text(account_name, product_group),
        }
        rows.append(row)

    # Embed the corpus in batches via Voyage AI. The same embedding_text is
    # stored on every document so Atlas Automated Embedding can re-derive
    # the same vector server-side from the text field on the MongoDB side.
    texts = [row["embedding_text"] for row in rows]
    print(
        f"Embedding {len(texts)} documents via Voyage AI "
        f"(model={voyage_model}, dim={embed_dim})..."
    )
    vectors = embed_documents(texts, voyage_api_key, voyage_model, embed_dim)
    for row, vec in zip(rows, vectors):
        row["embedding"] = vec
    return rows


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=settings.row_count)
    parser.add_argument("--dim", type=int, default=settings.embed_dim)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    if not 1000 <= args.rows <= 17000:
        raise SystemExit("--rows must be between 1000 and 17000")
    rows = generate(
        args.rows,
        args.dim,
        settings.voyage_api_key,
        settings.voyage_model,
        args.seed,
    )
    write_jsonl(rows, args.out)
    print(f"Wrote {len(rows)} synthetic rows to {args.out}")


if __name__ == "__main__":
    main()
