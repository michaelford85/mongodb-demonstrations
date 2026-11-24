"""A small, explicit configuration DSL for the operational change demo.

This is a demo-only constrained directive structure, validated locally. It is
NOT a general-purpose rules engine and does not represent any organization's
actual configuration model.
"""

ACTIONS = ("allow", "allow_with_tag", "deny")
MATCH_FIELDS = {
    "service_id",
    "request_type",
    "region",
    "environment",
}
CONFIG_STATUSES = ("draft", "pending_approval", "active", "superseded", "rejected")

ALLOWED_TRANSITIONS = {
    "draft": {"pending_approval", "rejected"},
    "pending_approval": {"active", "rejected"},
    "active": {"superseded"},
    "superseded": set(),
    "rejected": set(),
}


class ConfigValidationError(ValueError):
    """Raised when a configuration document violates the demo DSL."""


def _validate_directive(directive: dict, tag_ids: set, service_ids: set, seen_ids: set) -> list:
    errors: list = []
    if not isinstance(directive, dict):
        return [f"directive must be an object, got {type(directive).__name__}"]
    directive_id = directive.get("directive_id")
    if not directive_id or not isinstance(directive_id, str):
        errors.append("directive_id is required and must be a string")
    elif directive_id in seen_ids:
        errors.append(f"duplicate directive_id: {directive_id}")
    seen_ids.add(directive_id)

    priority = directive.get("priority")
    if not isinstance(priority, int) or isinstance(priority, bool):
        errors.append(f"{directive_id}: priority must be an integer")

    match = directive.get("match")
    if not isinstance(match, dict) or not match:
        errors.append(f"{directive_id}: match must be a non-empty object")
    else:
        unknown = set(match) - MATCH_FIELDS
        if unknown:
            errors.append(f"{directive_id}: unknown match fields {sorted(unknown)}")
        for scalar_field in ("service_id", "request_type", "region", "environment"):
            value = match.get(scalar_field)
            if value is not None and (not isinstance(value, str) or not value):
                errors.append(f"{directive_id}: match.{scalar_field} must be a non-empty string when present")

    action = directive.get("action")
    if action not in ACTIONS:
        errors.append(f"{directive_id}: action must be one of {list(ACTIONS)}")
    if action == "allow_with_tag":
        if not directive.get("tag_id"):
            errors.append(f"{directive_id}: allow_with_tag requires tag_id")
        elif tag_ids and directive["tag_id"] not in tag_ids:
            errors.append(f"{directive_id}: unknown tag_id {directive['tag_id']}")
    elif directive.get("tag_id"):
        errors.append(f"{directive_id}: tag_id is only allowed with allow_with_tag")

    match = directive.get("match") or {}
    service_id = match.get("service_id")
    if service_id is not None and service_ids and service_id not in service_ids:
        errors.append(f"{directive_id}: unknown service_id {service_id}")
    return errors


def validate_config(config: dict, tag_ids=None, service_ids=None, require_version=True) -> list:
    """Validate a configuration document against the demo DSL.

    Returns a list of human-readable error strings; empty list means valid.
    When tag_ids / service_ids are provided, referential integrity is checked
    against those catalogs. Drafts (require_version=False) skip the
    config_version check because a version is assigned only at publish time.
    """
    errors: list = []
    if not isinstance(config, dict):
        return ["config must be an object"]
    if not config.get("config_id") or not isinstance(config["config_id"], str):
        errors.append("config_id is required and must be a string")
    if require_version:
        version = config.get("config_version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            errors.append("config_version must be a positive integer")
    status = config.get("status", "draft")
    if status not in CONFIG_STATUSES:
        errors.append(f"status must be one of {list(CONFIG_STATUSES)}")
    default_action = config.get("default_action", "deny")
    if default_action not in ACTIONS:
        errors.append(f"default_action must be one of {list(ACTIONS)}")
    directives = config.get("directives")
    if not isinstance(directives, list) or not directives:
        errors.append("directives must be a non-empty list")
        return errors
    tag_ids = tag_ids if tag_ids is not None else set()
    service_ids = service_ids if service_ids is not None else None
    seen_ids: set = set()
    for directive in directives:
        errors.extend(_validate_directive(directive, tag_ids, service_ids, seen_ids))
    return errors


def check_transition(current_status: str, next_status: str) -> None:
    """Raise ConfigValidationError when the status transition is not permitted."""
    if current_status not in ALLOWED_TRANSITIONS:
        raise ConfigValidationError(f"unknown status {current_status!r}")
    if next_status not in ALLOWED_TRANSITIONS[current_status]:
        raise ConfigValidationError(
            f"transition {current_status!r} -> {next_status!r} is not permitted "
            f"(allowed: {sorted(ALLOWED_TRANSITIONS[current_status])})"
        )
