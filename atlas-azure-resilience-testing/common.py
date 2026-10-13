"""Shared helpers for the Atlas-on-Azure test harness.

Loads the folder's .env, resolves the run-artefact directory, and wraps the
Atlas Administration API with digest auth. API keys are read from the
environment only — they are never accepted as command-line arguments so they
cannot leak into shell history or process listings.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import requests
from dotenv import load_dotenv
from requests.auth import HTTPDigestAuth

ATLAS_API_BASE = "https://cloud.mongodb.com/api/atlas/v2"
ATLAS_API_VERSION = "2025-03-12"

STATE_NAMES = {
    0: "STARTUP",
    1: "PRIMARY",
    2: "SECONDARY",
    3: "RECOVERING",
    5: "STARTUP2",
    6: "UNKNOWN",
    7: "ARBITER",
    8: "DOWN",
    9: "ROLLBACK",
    10: "REMOVED",
}

_ROOT = Path(__file__).resolve().parent


def load_env() -> None:
    load_dotenv(_ROOT / ".env")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def scoped_uri(name: str) -> str:
    """Return the least-privilege URI called `name`, falling back to TEST_CLUSTER_URI.

    The provisioning folders create separate app, monitor and admin database
    users, so each script can connect with only the rights it needs. When the
    scoped variable is unset the script uses TEST_CLUSTER_URI, which keeps a
    single-user .env working.
    """
    return os.getenv(name) or require_env("TEST_CLUSTER_URI")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def results_dir() -> Path:
    path = _ROOT / os.getenv("RESULTS_DIR", "results")
    path.mkdir(parents=True, exist_ok=True)
    return path


def artefact_path(basename: str, suffix: str) -> Path:
    """Return a timestamped path under the results directory."""
    return results_dir() / f"{basename}-{utc_stamp()}.{suffix}"


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(f"Wrote {path}")


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def atlas_get(path: str, params: dict | None = None) -> dict:
    """GET an Atlas Administration API path relative to the v2 base."""
    auth = HTTPDigestAuth(
        require_env("ATLAS_PUBLIC_KEY"), require_env("ATLAS_PRIVATE_KEY")
    )
    response = requests.get(
        f"{ATLAS_API_BASE}{path}",
        auth=auth,
        headers={"Accept": f"application/vnd.atlas.{ATLAS_API_VERSION}+json"},
        params=params or {},
        timeout=30,
    )
    if response.status_code >= 400:
        # Body can echo request detail; surface status and endpoint only.
        raise SystemExit(
            f"Atlas API GET {path} failed with HTTP {response.status_code}"
        )
    return response.json()


def atlas_paginate(path: str, params: dict | None = None) -> Iterator[dict]:
    """Yield every result across paginated Atlas Administration API responses."""
    page = 1
    while True:
        query = dict(params or {})
        query.update({"pageNum": page, "itemsPerPage": 500})
        payload = atlas_get(path, query)
        results = payload.get("results", [])
        yield from results
        if len(results) < 500:
            return
        page += 1
