from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def fresh():
    return AppTest.from_file(APP, default_timeout=60).run()


def test_app_opens_without_running_anything_and_shows_empty_state():
    at = fresh()
    assert not at.exception
    assert "result" not in at.session_state
    assert any("No results yet" in i.value for i in at.info)
    assert [t.label for t in at.tabs] == ["1 · Configuration", "2 · Run", "3 · Results"]


def test_live_mode_is_blocked_without_credentials(monkeypatch):
    for var in ("MONGODB_URI", "VOYAGE_API_KEY", "COMPETITOR_API_KEY"):
        monkeypatch.setenv(var, "")
    at = fresh()
    at.radio[0].set_value(at.radio[0].options[1]).run()
    run_btn = next(b for b in at.button if b.label.startswith("▶"))
    assert run_btn.disabled


def test_dry_run_populates_results_without_secrets():
    at = fresh()
    next(b for b in at.button if b.label.startswith("▶")).click().run()
    assert not at.exception and not at.error
    result = at.session_state["result"]
    assert result["mock"] and result["status"] == "completed"
    assert any("Dry run" in w.value for w in at.warning)
    assert any("ndcg@10" in str(df.value) for df in at.dataframe)
    rerun = next(b for b in at.button if b.label.startswith("↻"))
    assert not rerun.disabled
