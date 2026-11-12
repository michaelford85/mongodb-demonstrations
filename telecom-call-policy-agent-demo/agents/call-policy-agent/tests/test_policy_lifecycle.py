"""Safety-critical tests: DSL validation, approval gating, versioning,
deterministic evaluation. Pure Python, no LLM, no network."""

import pytest

from agent_call_policy_agent.dsl import (
    ALLOWED_TRANSITIONS,
    PolicyValidationError,
    check_transition,
    validate_policy,
)
from agent_call_policy_agent.evaluator import compare_policies, evaluate_call
from agent_call_policy_agent.fixtures import ALL_FIXTURES
from agent_call_policy_agent.store import MemoryStore


@pytest.fixture()
def store():
    s = MemoryStore()
    s.ensure_seeded()
    return s


# ---------------------------------------------------------------------------
# DSL validation
# ---------------------------------------------------------------------------


def test_baseline_policy_is_valid():
    assert validate_policy(ALL_FIXTURES["policy_v1"]) == []


def test_rejects_unknown_action():
    bad = {**ALL_FIXTURES["policy_v1"], "rules": [{"rule_id": "r1", "priority": 1, "match": {"enterprise_id": "x"}, "action": "drop_call"}]}
    assert any("action" in e for e in validate_policy(bad))


def test_brand_required_for_deliver_with_brand():
    bad = {"policy_id": "p", "policy_version": 1, "rules": [{"rule_id": "r1", "priority": 1, "match": {"enterprise_id": "e"}, "action": "deliver_with_brand"}]}
    assert any("brand_id" in e for e in validate_policy(bad))


def test_unknown_brand_or_enterprise_rejected():
    rule = {"rule_id": "r1", "priority": 1, "match": {"enterprise_id": "nope"}, "action": "deliver_with_brand", "brand_id": "demo_brand_001"}
    errors = validate_policy(
        {"policy_id": "p", "policy_version": 1, "rules": [rule]},
        brand_ids={"demo_brand_001"},
        enterprise_ids={"demo_enterprise_001"},
    )
    assert any("unknown enterprise_id" in e for e in errors)

    rule["match"] = {"enterprise_id": "demo_enterprise_001"}
    rule["brand_id"] = "brand-nope"
    errors = validate_policy(
        {"policy_id": "p", "policy_version": 1, "rules": [rule]},
        brand_ids={"demo_brand_001"},
        enterprise_ids={"demo_enterprise_001"},
    )
    assert any("unknown brand_id" in e for e in errors)


def test_invalid_number_prefix_rejected():
    rule = {"rule_id": "r1", "priority": 1, "match": {"number_prefix": "1555"}, "action": "block"}
    assert any("number_prefix" in e for e in validate_policy(
        {"policy_id": "p", "policy_version": 1, "rules": [rule]}))


def test_transition_matrix_blocks_shortcuts():
    assert "active" not in ALLOWED_TRANSITIONS["draft"]
    assert ALLOWED_TRANSITIONS["rejected"] == set()
    with pytest.raises(PolicyValidationError):
        check_transition("draft", "active")
    with pytest.raises(PolicyValidationError):
        check_transition("rejected", "active")
    check_transition("pending_approval", "active")  # the only path to active


# ---------------------------------------------------------------------------
# Approval gating + versioning
# ---------------------------------------------------------------------------


def _draft(store):
    rules = [r for r in ALL_FIXTURES["policy_v1"]["rules"]]
    draft = store.save_draft({
        "draft_id": "draft-001",
        "policy_id": "demo-call-policy",
        "label": "test change",
        "rules": rules,
        "default_action": "block",
        "rationale": "test",
    })
    return draft


def test_publish_requires_approval(store):
    _draft(store)
    store.request_approval("draft-001", "summary")
    with pytest.raises(ValueError, match="no recorded human approval"):
        store.publish("draft-001")
    assert store.get_active_policy()["policy_version"] == 1  # unchanged


def test_denied_approval_cannot_be_published(store):
    _draft(store)
    store.request_approval("draft-001", "summary")
    store.record_approval("draft-001", "denied", "reviewer", "not convinced")
    with pytest.raises(ValueError, match="rejected"):
        store.publish("draft-001")
    assert store.get_active_policy()["policy_version"] == 1


def test_approved_draft_publishes_new_version_and_supersedes(store):
    _draft(store)
    store.request_approval("draft-001", "summary")
    store.record_approval("draft-001", "approved", "reviewer", "ok")
    published = store.publish("draft-001")
    assert published["policy_version"] == 2
    assert published["approved_by"] == "reviewer"
    active = store.get_active_policy()
    assert active["policy_version"] == 2
    versions = {p["policy_version"]: p["status"] for p in store.list_policies()}
    assert versions[1] == "superseded"
    assert versions[2] == "active"


def test_double_publish_rejected(store):
    _draft(store)
    store.request_approval("draft-001", "s")
    store.record_approval("draft-001", "approved", "r")
    store.publish("draft-001")
    with pytest.raises(ValueError, match="already active"):
        store.publish("draft-001")


def test_audit_trail_records_lifecycle(store):
    _draft(store)
    store.request_approval("draft-001", "s")
    store.record_approval("draft-001", "approved", "r")
    store.publish("draft-001")
    events = [a["event"] for a in store.audit_trail()]
    assert events == [
        "draft_created",
        "approval_requested",
        "approval_granted",
        "version_superseded",
        "version_published",
    ]


# ---------------------------------------------------------------------------
# Deterministic evaluation
# ---------------------------------------------------------------------------


def test_evaluator_matches_priority_rule():
    policy = ALL_FIXTURES["policy_v1"]
    result = evaluate_call(policy, ALL_FIXTURES["sample_calls"][0])
    assert result["decision"] == "deliver_with_brand"
    assert result["matched_rule"] == "rule-001"
    assert result["brand_id"] == "demo_brand_001"


def test_evaluator_default_blocks_unknown_number():
    policy = ALL_FIXTURES["policy_v1"]
    result = evaluate_call(policy, ALL_FIXTURES["sample_calls"][1])
    assert result["decision"] == "block"
    assert result["matched_rule"] is None


def test_collections_line_gets_servicing_brand():
    policy = ALL_FIXTURES["policy_v1"]
    result = evaluate_call(policy, ALL_FIXTURES["sample_calls"][3])
    assert result["decision"] == "deliver_with_brand"
    assert result["matched_rule"] == "rule-002"
    assert result["brand_id"] == "demo_brand_002"


def test_proposed_rule_changes_dry_run_diff():
    old = ALL_FIXTURES["policy_v1"]
    proposed = {
        "policy_version": "proposed",
        "rules": old["rules"] + [{
            "rule_id": "rule-003",
            "priority": 5,
            "match": {"origin_countries": ["GB"]},
            "action": "deliver",
            "rationale": "Allow GB traffic (fictional example)",
        }],
        "default_action": "block",
    }
    result = compare_policies(old, proposed, ALL_FIXTURES["sample_calls"])
    by_id = {r["call_id"]: r for r in result["rows"]}
    assert by_id["call-003"]["changed"] is True
    assert by_id["call-003"]["after"]["decision"] == "deliver"
    assert by_id["call-001"]["changed"] is False
    assert result["changed_count"] == 1


def test_draft_without_version_is_valid_but_published_doc_requires_it():
    draft = {
        "policy_id": "p",
        "rules": [{"rule_id": "r1", "priority": 1, "match": {"enterprise_id": "e"}, "action": "block"}],
    }
    assert validate_policy(draft, require_version=False) == []
    assert any("policy_version" in e for e in validate_policy(draft))
