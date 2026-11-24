"""Safety-critical tests: DSL validation, approval gating, versioning,
deterministic evaluation. Pure Python, no LLM, no network."""

import pytest

from agent_change_ops_agent.dsl import (
    ALLOWED_TRANSITIONS,
    ConfigValidationError,
    check_transition,
    validate_config,
)
from agent_change_ops_agent.evaluator import compare_configs, evaluate_case
from agent_change_ops_agent.fixtures import ALL_FIXTURES
from agent_change_ops_agent.store import MemoryStore


@pytest.fixture()
def store():
    s = MemoryStore()
    s.ensure_seeded()
    return s


# ---------------------------------------------------------------------------
# DSL validation
# ---------------------------------------------------------------------------


def test_baseline_config_is_valid():
    assert validate_config(ALL_FIXTURES["config_v1"]) == []


def test_rejects_unknown_action():
    bad = {
        **ALL_FIXTURES["config_v1"],
        "directives": [
            {
                "directive_id": "d1",
                "priority": 1,
                "match": {"service_id": "x"},
                "action": "delete_everything",
            }
        ],
    }
    assert any("action" in e for e in validate_config(bad))


def test_tag_required_for_allow_with_tag():
    bad = {
        "config_id": "c",
        "config_version": 1,
        "directives": [
            {"directive_id": "d1", "priority": 1, "match": {"service_id": "s"}, "action": "allow_with_tag"}
        ],
    }
    assert any("tag_id" in e for e in validate_config(bad))


def test_unknown_tag_or_service_rejected():
    directive = {
        "directive_id": "d1",
        "priority": 1,
        "match": {"service_id": "nope"},
        "action": "allow_with_tag",
        "tag_id": "demo_tag_001",
    }
    errors = validate_config(
        {"config_id": "c", "config_version": 1, "directives": [directive]},
        tag_ids={"demo_tag_001"},
        service_ids={"demo_service_001"},
    )
    assert any("unknown service_id" in e for e in errors)

    directive["match"] = {"service_id": "demo_service_001"}
    directive["tag_id"] = "tag-nope"
    errors = validate_config(
        {"config_id": "c", "config_version": 1, "directives": [directive]},
        tag_ids={"demo_tag_001"},
        service_ids={"demo_service_001"},
    )
    assert any("unknown tag_id" in e for e in errors)


def test_unknown_match_field_rejected():
    directive = {
        "directive_id": "d1",
        "priority": 1,
        "match": {"customer_name": "someone"},
        "action": "deny",
    }
    errors = validate_config({"config_id": "c", "config_version": 1, "directives": [directive]})
    assert any("unknown match fields" in e for e in errors)


def test_empty_directives_rejected():
    errors = validate_config({"config_id": "c", "config_version": 1, "directives": []})
    assert any("non-empty list" in e for e in errors)


def test_duplicate_directive_ids_rejected():
    directive = {"directive_id": "d1", "priority": 1, "match": {"service_id": "s"}, "action": "deny"}
    errors = validate_config(
        {"config_id": "c", "config_version": 1, "directives": [directive, dict(directive)]}
    )
    assert any("duplicate directive_id" in e for e in errors)


def test_transition_matrix_blocks_shortcuts():
    assert "active" not in ALLOWED_TRANSITIONS["draft"]
    assert ALLOWED_TRANSITIONS["rejected"] == set()
    with pytest.raises(ConfigValidationError):
        check_transition("draft", "active")
    with pytest.raises(ConfigValidationError):
        check_transition("rejected", "active")
    check_transition("pending_approval", "active")  # the only path to active


# ---------------------------------------------------------------------------
# Approval gating + versioning
# ---------------------------------------------------------------------------


def _draft(store):
    directives = [d for d in ALL_FIXTURES["config_v1"]["directives"]]
    draft = store.save_draft(
        {
            "draft_id": "draft-001",
            "config_id": "demo-op-config",
            "label": "test change",
            "directives": directives,
            "default_action": "deny",
            "rationale": "test",
        }
    )
    return draft


def test_publish_requires_approval(store):
    _draft(store)
    store.request_approval("draft-001", "summary")
    with pytest.raises(ValueError, match="no recorded human approval"):
        store.publish("draft-001")
    assert store.get_active_config()["config_version"] == 1  # unchanged


def test_publish_refused_with_no_approval_at_all(store):
    _draft(store)
    with pytest.raises(ValueError, match="no recorded human approval"):
        store.publish("draft-001")
    assert store.get_active_config()["config_version"] == 1


def test_denied_approval_cannot_be_published(store):
    _draft(store)
    store.request_approval("draft-001", "summary")
    store.record_approval("draft-001", "denied", "reviewer", "not convinced")
    with pytest.raises(ValueError, match="rejected"):
        store.publish("draft-001")
    assert store.get_active_config()["config_version"] == 1


def test_approved_draft_publishes_new_version_and_supersedes(store):
    _draft(store)
    store.request_approval("draft-001", "summary")
    store.record_approval("draft-001", "approved", "reviewer", "ok")
    published = store.publish("draft-001")
    assert published["config_version"] == 2
    assert published["approved_by"] == "reviewer"
    active = store.get_active_config()
    assert active["config_version"] == 2
    versions = {c["config_version"]: c["status"] for c in store.list_configs()}
    assert versions[1] == "superseded"
    assert versions[2] == "active"


def test_double_publish_rejected(store):
    _draft(store)
    store.request_approval("draft-001", "s")
    store.record_approval("draft-001", "approved", "r")
    store.publish("draft-001")
    with pytest.raises(ValueError, match="already active"):
        store.publish("draft-001")


def test_invalid_draft_status_cannot_skip_gate(store):
    _draft(store)
    store._replace("drafts", {"draft_id": "draft-001"}, {"status": "pending_approval"})
    with pytest.raises(ValueError, match="no recorded human approval"):
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


def test_evaluator_matches_priority_directive():
    config = ALL_FIXTURES["config_v1"]
    result = evaluate_case(config, ALL_FIXTURES["sample_cases"][0])
    assert result["outcome"] == "allow_with_tag"
    assert result["matched_directive"] == "dir-001"
    assert result["tag_id"] == "demo_tag_001"


def test_evaluator_default_denies_unknown_request_type():
    config = ALL_FIXTURES["config_v1"]
    result = evaluate_case(config, ALL_FIXTURES["sample_cases"][1])
    assert result["outcome"] == "deny"
    assert result["matched_directive"] is None


def test_priority_request_gets_priority_tag():
    config = ALL_FIXTURES["config_v1"]
    result = evaluate_case(config, ALL_FIXTURES["sample_cases"][3])
    assert result["outcome"] == "allow_with_tag"
    assert result["matched_directive"] == "dir-002"
    assert result["tag_id"] == "demo_tag_002"


def test_evaluation_is_deterministic(store):
    config = ALL_FIXTURES["config_v1"]
    case = ALL_FIXTURES["sample_cases"][2]
    assert evaluate_case(config, case) == evaluate_case(config, case)


def test_proposed_directive_changes_dry_run_diff():
    active = ALL_FIXTURES["config_v1"]
    proposed = {
        "config_version": "proposed",
        "directives": active["directives"]
        + [
            {
                "directive_id": "dir-003",
                "priority": 4,
                "match": {"service_id": "demo_service_002", "request_type": "standard"},
                "action": "allow",
                "rationale": "Allow provisioning service traffic (fictional example)",
            }
        ],
        "default_action": "deny",
    }
    result = compare_configs(active, proposed, ALL_FIXTURES["sample_cases"])
    by_id = {r["case_id"]: r for r in result["rows"]}
    assert by_id["case-003"]["changed"] is True
    assert by_id["case-003"]["after"]["outcome"] == "allow"
    assert by_id["case-001"]["changed"] is False
    assert result["changed_count"] == 1


def test_draft_without_version_is_valid_but_published_doc_requires_it():
    draft = {
        "config_id": "c",
        "directives": [
            {"directive_id": "d1", "priority": 1, "match": {"service_id": "s"}, "action": "deny"}
        ],
    }
    assert validate_config(draft, require_version=False) == []
    assert any("config_version" in e for e in validate_config(draft))


# ---------------------------------------------------------------------------
# Keyword fallback for change-note retrieval (mock mode)
# ---------------------------------------------------------------------------


def test_keyword_search_notes_matches_and_ranks(store):
    results = store.keyword_search_notes("provisioning service eu-demo-1")
    assert results
    assert results[0]["note_id"] == "note-001"


def test_keyword_search_notes_no_match_returns_empty(store):
    assert store.keyword_search_notes("zzz-no-such-term") == []


def test_vector_search_unavailable_in_mock_mode(store):
    assert store.vector_search_notes("anything") is None


# ---------------------------------------------------------------------------
# Reset scoping (MongoStore must drop ONLY demo collection names)
# ---------------------------------------------------------------------------


def test_mongostore_clear_demo_data_maps_collection_names(monkeypatch):
    """clear_demo_data drops collections by NAME, not via the logical-key map."""
    from agent_change_ops_agent import store as store_mod

    dropped = []

    class FakeCol:
        def __init__(self, name):
            self.name = name

        def drop(self):
            dropped.append(self.name)

        def create_index(self, *a, **k):
            pass

        def list_search_indexes(self):
            return []

    class FakeDB:
        def __getitem__(self, name):
            return FakeCol(name)

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __getitem__(self, db):
            return FakeDB()

        def close(self):
            pass

    s = store_mod.MongoStore("mongodb://localhost:27017", "change_ops_demo")
    monkeypatch.setattr(store_mod, "MongoClient", FakeClient)
    s.clear_demo_data()
    assert sorted(dropped) == sorted(set(store_mod.COLLECTIONS.values()))
    assert s._client is None
