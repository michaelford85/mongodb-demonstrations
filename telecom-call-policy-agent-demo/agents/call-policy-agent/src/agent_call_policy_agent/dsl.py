"""A small, explicit policy DSL for the fictional call-control demo.

This is a demo-only constrained rule structure, validated locally. It is
NOT a general-purpose rules engine and does not represent any organization.sactual policy model.
"""

ACTIONS = ("deliver", "deliver_with_brand", "block")
MATCH_FIELDS = {
    "enterprise_id",
    "carrier_id",
    "trunk_id",
    "origin_countries",
    "number_prefix",
}
POLICY_STATUSES = ("draft", "pending_approval", "active", "superseded", "rejected")

ALLOWED_TRANSITIONS = {
    "draft": {"pending_approval", "rejected"},
    "pending_approval": {"active", "rejected"},
    "active": {"superseded"},
    "superseded": set(),
    "rejected": set(),
}


class PolicyValidationError(ValueError):
    """Raised when a policy document violates the demo DSL."""


def _validate_rule(rule: dict, brand_ids: set, enterprise_ids: set, seen_rule_ids: set) -> list:
    errors: list = []
    if not isinstance(rule, dict):
        return [f"rule must be an object, got {type(rule).__name__}"]
    rule_id = rule.get("rule_id")
    if not rule_id or not isinstance(rule_id, str):
        errors.append("rule_id is required and must be a string")
    elif rule_id in seen_rule_ids:
        errors.append(f"duplicate rule_id: {rule_id}")
    seen_rule_ids.add(rule_id)

    priority = rule.get("priority")
    if not isinstance(priority, int) or isinstance(priority, bool):
        errors.append(f"{rule_id}: priority must be an integer")

    match = rule.get("match")
    if not isinstance(match, dict) or not match:
        errors.append(f"{rule_id}: match must be a non-empty object")
    else:
        unknown = set(match) - MATCH_FIELDS
        if unknown:
            errors.append(f"{rule_id}: unknown match fields {sorted(unknown)}")
        countries = match.get("origin_countries")
        if countries is not None and (
            not isinstance(countries, list)
            or not countries
            or not all(isinstance(c, str) and len(c) == 2 and c.isupper() for c in countries)
        ):
            errors.append(f"{rule_id}: origin_countries must be a non-empty list of ISO codes")
        prefix = match.get("number_prefix")
        if prefix is not None and not (isinstance(prefix, str) and prefix.startswith("+") and prefix[1:].isdigit()):
            errors.append(f"{rule_id}: number_prefix must be an E.164 prefix like '+1555'")

    action = rule.get("action")
    if action not in ACTIONS:
        errors.append(f"{rule_id}: action must be one of {list(ACTIONS)}")
    if action == "deliver_with_brand":
        if not rule.get("brand_id"):
            errors.append(f"{rule_id}: deliver_with_brand requires brand_id")
        elif brand_ids and rule["brand_id"] not in brand_ids:
            errors.append(f"{rule_id}: unknown brand_id {rule['brand_id']}")
    elif rule.get("brand_id"):
        errors.append(f"{rule_id}: brand_id is only allowed with deliver_with_brand")

    match = rule.get("match") or {}
    enterprise_id = match.get("enterprise_id")
    if enterprise_id is not None and enterprise_ids and enterprise_id not in enterprise_ids:
        errors.append(f"{rule_id}: unknown enterprise_id {enterprise_id}")
    return errors


def validate_policy(policy: dict, brand_ids=None, enterprise_ids=None) -> list:
    """Validate a policy document against the demo DSL.

    Returns a list of human-readable error strings; empty list means valid.
    When brand_ids / enterprise_ids are provided, referential integrity is
    checked against those catalogs.
    """
    errors: list = []
    if not isinstance(policy, dict):
        return ["policy must be an object"]
    if not policy.get("policy_id") or not isinstance(policy["policy_id"], str):
        errors.append("policy_id is required and must be a string")
    version = policy.get("policy_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        errors.append("policy_version must be a positive integer")
    status = policy.get("status", "draft")
    if status not in POLICY_STATUSES:
        errors.append(f"status must be one of {list(POLICY_STATUSES)}")
    default_action = policy.get("default_action", "block")
    if default_action not in ACTIONS:
        errors.append(f"default_action must be one of {list(ACTIONS)}")
    rules = policy.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append("rules must be a non-empty list")
        return errors
    brand_ids = brand_ids if brand_ids is not None else set()
    enterprise_ids = enterprise_ids if enterprise_ids is not None else None
    seen_rule_ids: set = set()
    for rule in rules:
        errors.extend(_validate_rule(rule, brand_ids, enterprise_ids, seen_rule_ids))
    return errors


def check_transition(current_status: str, next_status: str) -> None:
    """Raise PolicyValidationError when the status transition is not permitted."""
    if current_status not in ALLOWED_TRANSITIONS:
        raise PolicyValidationError(f"unknown status {current_status!r}")
    if next_status not in ALLOWED_TRANSITIONS[current_status]:
        raise PolicyValidationError(
            f"transition {current_status!r} -> {next_status!r} is not permitted "
            f"(allowed: {sorted(ALLOWED_TRANSITIONS[current_status])})"
        )
