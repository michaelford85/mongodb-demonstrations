"""Shared configuration and clients for the demo scripts and app."""

from __future__ import annotations

import os

from dotenv import load_dotenv


def load_config() -> dict:
    load_dotenv()
    cfg = {
        "atlas_uri": os.environ["ATLAS_URI"],
        "database": os.environ.get("ATLAS_DATABASE", "enterprise_search_demo"),
        "collection": os.environ.get("ATLAS_COLLECTION", "search_items"),
        "voyage_api_key": os.environ["VOYAGE_API_KEY"],
        "voyage_model": os.environ.get("VOYAGE_MODEL", "voyage-3.5"),
        "voyage_dimensions": int(os.environ.get("VOYAGE_DIMENSIONS", "1024")),
        "pg": {
            k.lower(): v
            for k, v in {
                "host": os.environ["PG_HOST"],
                "port": int(os.environ.get("PG_PORT", "5432")),
                "dbname": os.environ.get("PG_DATABASE", "demodb"),
                "user": os.environ.get("PG_USER", "demo_dml"),
                "password": os.environ["PG_PASSWORD"],
                "schema": os.environ.get("PG_SCHEMA", "demo_schema"),
                "table": os.environ.get("PG_TABLE", "knowledge_items"),
            }.items()
        },
    }
    if cfg["voyage_dimensions"] not in (256, 512, 1024, 2048):
        raise ValueError(
            f"VOYAGE_DIMENSIONS={cfg['voyage_dimensions']} is not supported by "
            "{voyage-3.5}; use 256, 512, 1024 (default), or 2048."
        )
    return cfg


def atlas_collection(cfg: dict):
    from pymongo import MongoClient

    return MongoClient(cfg["atlas_uri"])[cfg["database"]][cfg["collection"]]


def voyage_embed(
    cfg: dict,
    texts: list[str],
    input_type: str = "document",
) -> list[list[float]]:
    """Embed via the Voyage AI REST API (no SDK dependency)."""
    import urllib.request

    body = {
        "input": texts,
        "model": cfg["voyage_model"],
        "input_type": input_type,
        "output_dimension": cfg["voyage_dimensions"],
    }
    req = urllib.request.Request(
        "https://api.voyageai.com/v1/embeddings",
        data=__import__("json").dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['voyage_api_key']}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = __import__("json").loads(resp.read())
    return [item["embedding"] for item in payload["data"]]
