import json

from config import HARD_LIMITS, load_config, summarize
from metrics import milestone_summary


def test_region_names_parsed_from_comma_list():
    cfg = load_config(env={"ATLAS_BENCHMARK_REGIONS": "eastus, swedencentral , ,westus"})
    assert cfg.region_names == ["eastus", "swedencentral", "westus"]


def test_empty_regions_is_empty_list():
    cfg = load_config(env={"ATLAS_BENCHMARK_REGIONS": ""})
    assert cfg.region_names == []


def test_negative_validation_window_rejected():
    cfg = load_config(env={"INDEX_VALIDATION_WINDOW_SECONDS": "-1"})
    assert any("validation_window_seconds" in p for p in cfg.problems)


def test_topology_metadata_recorded_in_plan():
    cfg = load_config(env={"ATLAS_BENCHMARK_REGIONS": "a,b",
                           "SEARCH_NODE_COUNT": "2 per region",
                           "SEARCH_NODE_TIER": "S10"})
    plan = summarize(cfg)
    meta = plan["manual_metadata"]
    assert meta["region_names"] == ["a", "b"]
    assert meta["search_node_count"] == "2 per region"
    assert meta["search_node_tier"] == "S10"
    assert "not inferred" in meta["note"]
    assert plan["validation_window_seconds"] == 30.0


def test_milestone_summary_elapsed_from_first():
    milestones = {
        "create_request": "2026-10-21T22:00:00+00:00",
        "first_query": "2026-10-21T22:00:10.500+00:00",
        "sustained_passed": "2026-10-21T22:01:10.500+00:00",
    }
    out = milestone_summary(milestones)
    assert out["create_request"] == 0.0
    assert out["first_query"] == 10.5
    assert out["sustained_passed"] == 70.5


def test_milestone_summary_handles_missing_values():
    out = milestone_summary({"a": None, "b": "2026-01-01T00:00:05+00:00"})
    assert out["a"] is None
    assert out["b"] == 0.0


def test_milestone_summary_serializable():
    out = milestone_summary({"x": "2026-01-01T00:00:00+00:00"})
    assert json.loads(json.dumps(out)) == {"x": 0.0}
