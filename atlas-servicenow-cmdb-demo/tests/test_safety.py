import pytest

import run_demo
from servicenow_client import ServiceNowIREClient, ServiceNowError, ensure_apply_allowed


class FakeSession:
    def __init__(self, status=200, body=None):
        self.status = status
        self.body = body or {"result": []}
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs.get("params"), kwargs.get("json")))
        return _Resp(self.status, self.body)


class _Resp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.headers = {}

    def json(self):
        return self._body


def make_client(session):
    return ServiceNowIREClient(
        instance_url="https://example.service-now.com",
        username="u",
        password="p",
        discovery_source="atlas",
        session=session,
        sleeper=lambda s: None,
    )


def test_apply_without_flag_aborts():
    settings = run_demo.load_settings(env={"SERVICENOW_ALLOW_WRITES": "true"})
    with pytest.raises(SystemExit, match="--apply"):
        ensure_apply_allowed(settings, cli_apply=False)


def test_apply_without_env_opt_in_aborts():
    settings = run_demo.load_settings(env={"SERVICENOW_ALLOW_WRITES": "false"})
    with pytest.raises(SystemExit, match="SERVICENOW_ALLOW_WRITES"):
        ensure_apply_allowed(settings, cli_apply=True)


def test_apply_requires_both_flag_and_env():
    settings = run_demo.load_settings(env={"SERVICENOW_ALLOW_WRITES": "true"})
    ensure_apply_allowed(settings, cli_apply=True)


def test_submit_uses_ire_endpoint_with_data_source():
    session = FakeSession()
    make_client(session).submit({"items": [], "relations": []})
    url, params, body = session.calls[0]
    assert url == "https://example.service-now.com/api/now/identifyreconcile"
    assert params == {"sysparm_data_source": "atlas"}
    assert body == {"items": [], "relations": []}


def test_simulate_uses_query_endpoint_not_submit():
    session = FakeSession()
    make_client(session).simulate({"items": [], "relations": []})
    url, _, _ = session.calls[0]
    assert url.endswith("/api/now/identifyreconcile/query")


def test_client_requires_configuration():
    with pytest.raises(ServiceNowError):
        ServiceNowIREClient(instance_url="", username="u", password="p", discovery_source="atlas")
    with pytest.raises(ServiceNowError):
        ServiceNowIREClient(instance_url="https://x", username="", password="", discovery_source="atlas")


def test_dry_run_makes_no_servicenow_calls(tmp_path):
    exit_code = run_demo.main(["--source", "mock", "--quiet"])
    assert exit_code == 0
    artifacts = list((run_demo.OUTPUT_DIR).glob("*.json"))
    assert any(p.name == "ire_payload.json" for p in artifacts)
    assert any(p.name == "normalized_inventory.json" for p in artifacts)


def test_validate_is_allowed_without_write_opt_in():
    session = FakeSession()
    client = make_client(session)
    client.simulate({"items": [], "relations": []})
    assert session.calls[0][0].endswith("/identifyreconcile/query")


def test_apply_run_via_cli_requires_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SERVICENOW_ALLOW_WRITES", "false")
    with pytest.raises(SystemExit, match="SERVICENOW_ALLOW_WRITES"):
        run_demo.main(["--source", "mock", "--quiet", "--apply"])
