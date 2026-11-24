"""Deterministic operational-change evaluation.

This module is intentionally free of any LLM or Agent Engine imports: the
live request path must stay deterministic and use the published configuration
snapshot. Embeddings/semantic retrieval may help FIND context; they never make
or execute this decision.
"""

from typing import Any, Optional

MATCH_KEYS = ("service_id", "request_type", "region", "environment")


def _directive_matches(directive: dict, case: dict) -> bool:
    match = directive.get("match", {})
    for key in MATCH_KEYS:
        expected = match.get(key)
        if expected is not None and case.get(key) != expected:
            return False
    return True


def evaluate_case(config: dict, case: dict) -> dict:
    """Evaluate one sample case against a published configuration snapshot.

    First match wins by ascending priority. Returns the outcome, the matched
    directive, and a human-readable reason. No model calls.
    """
    config_version = config.get("config_version")
    directives = sorted(config.get("directives", []), key=lambda d: d.get("priority", 0))
    for directive in directives:
        if _directive_matches(directive, case):
            action = directive.get("action")
            result: dict[str, Any] = {
                "outcome": action,
                "matched_directive": directive.get("directive_id"),
                "config_version": config_version,
                "reason": directive.get("rationale", f"matched directive {directive.get('directive_id')}"),
            }
            if action == "allow_with_tag":
                result["tag_id"] = directive.get("tag_id")
            return result
    return {
        "outcome": config.get("default_action", "deny"),
        "matched_directive": None,
        "config_version": config_version,
        "reason": "no directive matched; default_action applied",
    }


def compare_configs(old_config: dict, new_config: dict, sample_cases: list) -> dict:
    """Dry-run active vs. proposed configuration over sample cases."""
    rows = []
    for case in sample_cases:
        before = evaluate_case(old_config, case)
        after = evaluate_case(new_config, case)
        rows.append(
            {
                "case_id": case.get("case_id"),
                "description": case.get("description"),
                "before": before,
                "after": after,
                "changed": before["outcome"] != after["outcome"]
                or before.get("tag_id") != after.get("tag_id"),
            }
        )
    return {
        "sample_count": len(rows),
        "changed_count": sum(1 for r in rows if r["changed"]),
        "rows": rows,
    }


def active_config_snapshot(configs: list) -> Optional[dict]:
    """Return the active configuration document from a list of versions."""
    for config in configs:
        if config.get("status") == "active":
            return config
    return None
