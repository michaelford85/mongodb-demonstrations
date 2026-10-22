from metrics import latency_summary, percentile, save_results, to_markdown


def test_percentile_nearest_rank():
    values = list(range(1, 101))  # 1..100
    assert percentile(values, 50) == 50
    assert percentile(values, 90) == 90
    assert percentile(values, 95) == 95
    assert percentile(values, 99) == 99
    assert percentile(values, 100) == 100


def test_percentile_edge_cases():
    assert percentile([], 50) is None
    assert percentile([5.0], 99) == 5.0
    assert percentile([1.0, 2.0], 0) == 1.0


def test_latency_summary_keys():
    summary = latency_summary([10.0, 20.0, 30.0, 40.0, 100.0])
    assert summary["count"] == 5
    assert summary["p50_ms"] == 30.0
    assert summary["max_ms"] == 100.0
    assert set(summary) == {"count", "p50_ms", "p90_ms", "p95_ms", "p99_ms", "max_ms"}


def test_save_results_writes_json_and_md(tmp_path):
    results = {"run_id": "r1", "utc_start": "s", "utc_end": "e",
               "phases": {"load": {"achieved_qps": 4.9}}}
    json_path, md_path = save_results(results, str(tmp_path), "r1")
    assert json_path.endswith("r1.json") and md_path.endswith("r1.md")
    assert "achieved_qps" in open(json_path).read()
    assert "achieved_qps" in open(md_path).read()


def test_markdown_has_warning_and_operator_sections():
    results = {"run_id": "r2", "phases": {},
               "warnings": ["w1"], "operator_recorded": ["o1"]}
    md = to_markdown(results)
    assert "w1" in md and "o1" in md
