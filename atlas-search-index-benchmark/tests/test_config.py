import json
import os

import pytest

from config import HARD_LIMITS, BenchmarkConfig, load_config, validate


def test_default_config_is_plan_only():
    cfg = load_config(env={})
    assert cfg.live_allowed is False
    assert cfg.allow_writes is False
    assert cfg.confirmed is False
    assert cfg.uri == ""
    assert cfg.problems == []


def test_write_gate_requires_all_three():
    env = {"ATLAS_BENCHMARK_URI": "mongodb+srv://u:p@host/",
           "ALLOW_ATLAS_BENCHMARK_WRITES": "true"}
    cfg = load_config(env=env)
    assert not cfg.live_allowed and not cfg.confirmed
    env["BENCHMARK_CONFIRM"] = "yes"
    cfg = load_config(env=env)
    assert cfg.live_allowed


def test_qps_over_hard_cap_is_rejected():
    env = {"LOAD_QPS": str(HARD_LIMITS["max_qps"] + 1)}
    cfg = load_config(env=env)
    assert any("hard cap" in p for p in cfg.problems)


def test_doc_count_over_hard_cap_is_rejected():
    cfg = load_config(env={"DOC_COUNT": str(HARD_LIMITS["max_doc_count"] + 1)})
    assert any("hard cap" in p for p in cfg.problems)


def test_malformed_number_is_rejected():
    with pytest.raises(ValueError):
        load_config(env={"LOAD_QPS": "banana"})


def test_negative_value_is_rejected():
    cfg = load_config(env={"DOC_COUNT": "-5"})
    assert any("doc_count" in p for p in cfg.problems)


def test_write_churn_requires_write_gate():
    env = {"MIXED_INSERT_PER_SEC": "10", "ATLAS_BENCHMARK_URI": "mongodb+srv://u:p@h/"}
    cfg = load_config(env=env)
    assert any("ALLOW_ATLAS_BENCHMARK_WRITES" in p for p in cfg.problems)


def test_missing_index_definition_file_flagged():
    cfg = load_config(env={"ATLAS_BENCHMARK_INDEX_DEFINITION": "/nope/missing.json"})
    assert any("index_definition_file" in p for p in cfg.problems)


def test_gate_without_uri_flagged():
    cfg = load_config(env={"ALLOW_ATLAS_BENCHMARK_WRITES": "true"})
    assert any("ATLAS_BENCHMARK_URI" in p for p in cfg.problems)
