"""Deterministic call-control call evaluation.

This module is intentionally free of any LLM or Agent Engine imports: the
live call path must stay deterministic and use the published policy snapshot.
"""

from typing import Any, Optional

PERMITTED_KEYS = ("enterprise_id", "carrier_id", "trunk_id", "origin_countries", "number_prefix")


def _rule_matches(rule: dict, call: dict) -> bool:
    match = rule.get("match", {})
    enterprise_id = match.get("enterprise_id")
    if enterprise_id is not None and call.get("enterprise_id") != enterprise_id:
        return False
    carrier_id = match.get("carrier_id")
    if carrier_id is not None and call.get("carrier_id") != carrier_id:
        return False
    trunk_id = match.get("trunk_id")
    if trunk_id is not None and call.get("trunk_id") != trunk_id:
        return False
    countries = match.get("origin_countries")
    if countries is not None and call.get("origin_country") not in countries:
        return False
    prefix = match.get("number_prefix")
    if prefix is not None and not str(call.get("from_number", "")).startswith(prefix):
        return False
    return True


def evaluate_call(policy: dict, call: dict) -> dict:
    """Evaluate one call against a published policy snapshot.

    First match wins by ascending priority. Returns the decision, the
    matched rule, and a human-readable reason. No model calls.
    """
    policy_version = policy.get("policy_version")
    rules = sorted(policy.get("rules", []), key=lambda r: r.get("priority", 0))
    for rule in rules:
        if _rule_matches(rule, call):
            action = rule.get("action")
            result: dict[str, Any] = {
                "decision": action,
                "matched_rule": rule.get("rule_id"),
                "policy_version": policy_version,
                "reason": rule.get("rationale", f"matched rule {rule.get('rule_id')}"),
            }
            if action == "deliver_with_brand":
                result["brand_id"] = rule.get("brand_id")
            return result
    return {
        "decision": policy.get("default_action", "block"),
        "matched_rule": None,
        "policy_version": policy_version,
        "reason": "no rule matched; default_action applied",
    }


def compare_policies(old_policy: dict, new_policy: dict, sample_calls: list) -> dict:
    """Dry-run old vs. proposed policy over sample calls."""
    rows = []
    for call in sample_calls:
        before = evaluate_call(old_policy, call)
        after = evaluate_call(new_policy, call)
        rows.append(
            {
                "call_id": call.get("call_id"),
                "description": call.get("description"),
                "before": before,
                "after": after,
                "changed": before["decision"] != after["decision"]
                or before.get("brand_id") != after.get("brand_id"),
            }
        )
    return {
        "sample_count": len(rows),
        "changed_count": sum(1 for r in rows if r["changed"]),
        "rows": rows,
    }


def active_policy_snapshot(policies: list) -> Optional[dict]:
    """Return the active policy document from a list of policy versions."""
    for policy in policies:
        if policy.get("status") == "active":
            return policy
    return None
