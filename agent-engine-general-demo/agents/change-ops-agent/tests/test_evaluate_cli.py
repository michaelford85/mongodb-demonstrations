"""Focused tests for evaluate_cli database-selection precedence.

These tests never connect to MongoDB, never invoke an LLM, and never read a
developer's real .env: they run in temporary directories with a temporary
.env file and a mocked store factory.
"""

import sys

import pytest

from agent_change_ops_agent import evaluate_cli
from agent_change_ops_agent.fixtures import ALL_FIXTURES


class FakeStore:
    mode = "mock"

    def __init__(self, expected_database):
        self.expected_database = expected_database
        self.seeded = False

    def ensure_seeded(self):
        self.seeded = True

    def get_active_config(self):
        return ALL_FIXTURES["config_v1"]

    def list_sample_cases(self):
        return [{"kind": "sample_cases", "data": c} for c in ALL_FIXTURES["sample_cases"]]


@pytest.fixture()
def cli_env(tmp_path, monkeypatch):
    """Isolate the test: temp cwd with its own .env, clean MONGODB_* env vars."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MONGODB_DATABASE", raising=False)
    monkeypatch.delenv("MONGODB_URI", raising=False)
    captured = {}

    def fake_create_store(uri, database):
        captured["uri"] = uri
        captured["database"] = database
        return FakeStore(database)

    monkeypatch.setattr(evaluate_cli, "create_store", fake_create_store)
    return tmp_path, captured


def _run_main(monkeypatch, *argv):
    printer = []
    monkeypatch.setattr(sys, "argv", ["evaluate_cli", *argv])
    monkeypatch.setattr("builtins.print", lambda *a, **k: printer.append(" ".join(map(str, a))))
    assert evaluate_cli.main() == 0
    return printer


def test_env_supplies_database_when_no_flag_or_export(cli_env, monkeypatch):
    tmp_path, captured = cli_env
    (tmp_path / ".env").write_text("MONGODB_DATABASE=from_dotenv_db\n", encoding="utf-8")
    _run_main(monkeypatch)
    assert captured["database"] == "from_dotenv_db"


def test_exported_variable_beats_dotenv(cli_env, monkeypatch):
    tmp_path, captured = cli_env
    (tmp_path / ".env").write_text("MONGODB_DATABASE=from_dotenv_db\n", encoding="utf-8")
    monkeypatch.setenv("MONGODB_DATABASE", "exported_db")
    _run_main(monkeypatch)
    assert captured["database"] == "exported_db"


def test_cli_flag_beats_env_and_dotenv(cli_env, monkeypatch):
    tmp_path, captured = cli_env
    (tmp_path / ".env").write_text("MONGODB_DATABASE=from_dotenv_db\n", encoding="utf-8")
    monkeypatch.setenv("MONGODB_DATABASE", "exported_db")
    _run_main(monkeypatch, "--database", "flag_db")
    assert captured["database"] == "flag_db"


def test_cli_still_deterministic_and_offline(cli_env, monkeypatch):
    """Sample-case path prints deterministic outcomes and never needs a URI."""
    tmp_path, captured = cli_env
    output = "\n".join(_run_main(monkeypatch))
    assert captured["uri"] == ""  # mock mode: no connection string used
    assert "allow_with_tag" in output
    assert "demo_tag_001" in output
