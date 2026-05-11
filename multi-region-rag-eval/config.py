"""Shared configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    pg_conn_str: str
    mongo_uri: str
    mongo_db: str
    mongo_collection: str
    pg_table: str
    embed_dim: int
    row_count: int
    atlas_vector_index: str


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is not set.")
    return value


def load_settings() -> Settings:
    row_count = int(os.getenv("ROW_COUNT", "5000"))
    if not 1000 <= row_count <= 17000:
        raise ValueError("ROW_COUNT must be between 1000 and 17000.")
    embed_dim = int(os.getenv("EMBED_DIM", "1024"))
    if embed_dim not in (1024, 2000):
        raise ValueError("EMBED_DIM must be 1024 or 2000.")
    return Settings(
        pg_conn_str=_require("PG_CONN_STR"),
        mongo_uri=_require("MONGO_URI"),
        mongo_db=os.getenv("MONGO_DB", "routing_demo"),
        mongo_collection=os.getenv("MONGO_COLLECTION", "accounts"),
        pg_table=os.getenv("PG_TABLE", "accounts"),
        embed_dim=embed_dim,
        row_count=row_count,
        atlas_vector_index=os.getenv("ATLAS_VECTOR_INDEX", "accounts_vector_idx"),
    )


REGIONS = ("France", "Italy", "Germany", "Spain", "UK")
PRODUCT_GROUPS = ("Hardware", "Software", "Services", "Subscriptions", "Consulting")
CASE_REASONS = (
    "Billing Inquiry",
    "Technical Issue",
    "Renewal",
    "Onboarding",
    "Cancellation",
    "Upgrade",
)
SALES_AREAS = ("EMEA-North", "EMEA-South", "EMEA-West", "EMEA-Central")
