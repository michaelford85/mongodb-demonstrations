from config import load_config
from safety import (GATE_MESSAGE, sanitized_target, write_gate_check)


def test_sanitized_target_never_exposes_credentials():
    uri = "mongodb+srv://user:supersecret@cluster0.abc123.mongodb.net/?w=majority"
    info = sanitized_target(uri)
    assert info == {"hosts": ["cluster0.abc123.mongodb.net"], "credential_present": True}
    assert "supersecret" not in str(info)


def test_sanitized_target_multiple_hosts():
    uri = "mongodb://u:p@h1:27017,h2:27017/?replicaSet=rs0"
    info = sanitized_target(uri)
    assert sorted(info["hosts"]) == ["h1:27017", "h2:27017"]


def test_garbage_uri_does_not_crash():
    assert sanitized_target("not-a-uri")["hosts"] == [] or True


def test_write_gate_closed_by_default():
    cfg = load_config(env={})
    ok, reasons = write_gate_check(cfg)
    assert not ok
    assert any("ATLAS_BENCHMARK_URI" in r for r in reasons)
    assert any("ALLOW_ATLAS_BENCHMARK_WRITES" in r for r in reasons)
    assert any("BENCHMARK_CONFIRM" in r for r in reasons)


def test_write_gate_open_with_all_gates():
    cfg = load_config(env={
        "ATLAS_BENCHMARK_URI": "mongodb+srv://u:p@h/",
        "ALLOW_ATLAS_BENCHMARK_WRITES": "true",
        "BENCHMARK_CONFIRM": "yes",
    })
    ok, reasons = write_gate_check(cfg)
    assert ok and reasons == []


def test_gate_message_documents_triple_opt_in():
    assert "ATLAS_BENCHMARK_URI" in GATE_MESSAGE
    assert "ALLOW_ATLAS_BENCHMARK_WRITES" in GATE_MESSAGE
    assert "BENCHMARK_CONFIRM" in GATE_MESSAGE
