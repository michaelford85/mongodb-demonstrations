"""Plan-only default behavior: with no env and no network, the default phase
must print a plan, keep the gate CLOSED, and attempt no writes."""
import json
import os
import subprocess
import sys

from config import load_config


def test_plan_phase_default_offline(tmp_path):
    env = dict(os.environ)
    env.pop("ATLAS_BENCHMARK_URI", None)
    env.pop("ALLOW_ATLAS_BENCHMARK_WRITES", None)
    env.pop("BENCHMARK_CONFIRM", None)
    env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["BENCHMARK_NO_DOTENV"] = "1"  # isolate the test from any local .env
    proc = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "benchmark.py"), "plan"],
        capture_output=True, text=True, env=env, timeout=30,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert proc.returncode == 0
    # Plan output contains no credentials/URI echo.
    assert "mongodb+srv" not in proc.stdout
    assert "gate_status" in proc.stdout
    out = proc.stdout
    plan = json.loads(out[out.index("{"): out.rindex("}") + 1])
    assert plan["gate_status"] == "CLOSED (plan-only)"
    assert plan["will_write_anything"] is False
    assert plan["namespace"] == "search_bench_demo.bench_docs"


def test_default_namespace_is_demo_dedicated():
    cfg = load_config(env={})
    assert cfg.namespace == "search_bench_demo.bench_docs"
    assert "prod" not in cfg.namespace
