#!/usr/bin/env python3
"""Utilities to scale an Atlas cluster using the Atlas Admin API."""

from __future__ import annotations

import os
from typing import Dict

import requests
from requests.auth import HTTPDigestAuth


class ConfigError(RuntimeError):
    """Raised when required environment configuration is missing."""


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def build_config(target_tier_env: str) -> Dict[str, str]:
    return {
        "public_key": _required_env("ATLAS_PUBLIC_KEY"),
        "private_key": _required_env("ATLAS_PRIVATE_KEY"),
        "project_id": _required_env("ATLAS_PROJECT_ID"),
        "cluster_name": _required_env("ATLAS_CLUSTER_NAME"),
        "target_tier": _required_env(target_tier_env),
        "base_url": os.getenv("ATLAS_BASE_URL", "https://cloud.mongodb.com/api/atlas/v2"),
    }


def scale_cluster(target_tier_env: str) -> None:
    cfg = build_config(target_tier_env)
    url = (
        f"{cfg['base_url']}/groups/{cfg['project_id']}/clusters/{cfg['cluster_name']}"
    )

    payload = {
        "providerSettings": {
            "instanceSizeName": cfg["target_tier"],
        }
    }

    response = requests.patch(
        url,
        auth=HTTPDigestAuth(cfg["public_key"], cfg["private_key"]),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()

    print(
        f"Requested scale for cluster '{cfg['cluster_name']}' "
        f"in project '{cfg['project_id']}' to tier '{cfg['target_tier']}'."
    )
    print("Atlas accepted the request. Scaling proceeds asynchronously.")
