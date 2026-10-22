"""Safety helpers: URI sanitization, write gate, cleanup confirmation.

Nothing in this demo ever prints credentials or a full connection string.
"""
from __future__ import annotations

import hashlib
import json
import os

WARNING = (
    "*** WARNING: run only against a NON-PRODUCTION test cluster unless an "
    "authorized cluster owner has reviewed and explicitly approved this run. ***"
)

GATE_MESSAGE = (
    "Live actions are blocked. To enable writes/load:\n"
    "  1. Set ATLAS_BENCHMARK_URI to a non-production cluster URI.\n"
    "  2. Set ALLOW_ATLAS_BENCHMARK_WRITES=true\n"
    "  3. Set BENCHMARK_CONFIRM=yes (explicit operator confirmation).\n"
    "Default mode is plan-only and performs no writes."
)


def sanitized_target(uri: str) -> dict:
    """Return host label(s) and database for display. Never credentials."""
    try:
        rest = uri.split("://", 1)[1] if "://" in uri else uri
        creds, _, hostpart = rest.rpartition("@")
        hostpart = hostpart.split("/", 1)[0].split("?", 1)[0]
        hosts = [h.strip() for h in hostpart.split(",") if h.strip()]
    except Exception:
        hosts = []
    return {"hosts": hosts, "credential_present": bool(creds)}


def sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def write_gate_check(cfg) -> tuple[bool, list[str]]:
    """Verify all gates for any live (writing) phase. Returns (ok, reasons)."""
    reasons = []
    if not cfg.uri:
        reasons.append("ATLAS_BENCHMARK_URI is not set")
    if not cfg.allow_writes:
        reasons.append("ALLOW_ATLAS_BENCHMARK_WRITES is not true")
    if not cfg.confirmed:
        reasons.append("BENCHMARK_CONFIRM is not yes")
    if cfg.problems:
        reasons.extend(f"config problem: {p}" for p in cfg.problems)
    return (not reasons), reasons


def interactive_confirm(target: dict, namespace: str, action: str, cfg) -> bool:
    """Preview sanitized target and require confirmation unless assume_yes."""
    print(WARNING)
    print(f"Action          : {action}")
    print(f"Cluster (hosts) : {target['hosts'] or '<unparseable>'}")
    print(f"Namespace       : {namespace}")
    print("Credentials are never displayed.")
    if not write_gate_check(cfg)[0]:
        print(GATE_MESSAGE)
        return False
    if cfg.assume_yes:
        print("BENCHMARK_ASSUME_YES=true: proceeding without interactive prompt.")
        return True
    answer = input("Type 'CONFIRM' to proceed: ")
    return answer.strip() == "CONFIRM"


def cleanup_preview(namespace: str, search_index_name: str) -> dict:
    return {
        "will_drop_search_index": search_index_name,
        "will_drop_collection": namespace,
        "will_drop_database": False,
        "will_touch_other_namespaces": False,
        "note": "Never drops a database. Limited to the demo-owned namespace only.",
    }


def load_json_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def ensure_results_dir(base: str) -> str:
    path = os.path.join(base, "results")
    os.makedirs(path, exist_ok=True)
    return path
