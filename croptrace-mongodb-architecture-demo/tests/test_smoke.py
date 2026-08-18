"""Smoke tests for the CropTrace architecture demo.

Offline checks compile every page/script, import every library module, and
exercise the pure builders and the local embedder — so `pytest` passes with no
Atlas cluster. The connectivity-guarded check runs the readiness suite when a
cluster is reachable and skips cleanly otherwise, so tests never fail for
environmental reasons.

Run: python3 -m pytest tests -v
"""

import py_compile
from pathlib import Path

import pytest

from lib.ai import _cosine, _extractive_answer
from lib.atlas_client import PLOT_IDS, PRODUCT_IDS, ping
from lib.embeddings import LocalEmbedder, embedding_dim
from lib.knowledge import NOTES, note_text
from lib.master_data import RESOLVED_FIELDS, SNAPSHOT_FIELDS
from lib.queries import RELEVANT_INDEXES, residue_decision_pipeline
from lib.sample_data import build_crops, build_plots_and_events, build_products

ROOT = Path(__file__).parent.parent


def test_all_pages_and_scripts_compile():
    targets = sorted(ROOT.glob("pages/*.py")) + sorted(ROOT.glob("scripts/*.py"))
    targets += [ROOT / "app.py", ROOT / "seed_data.py", ROOT / "teardown.py"]
    assert targets, "expected page/script files to compile"
    for path in targets:
        py_compile.compile(str(path), doraise=True)


def test_library_modules_import():
    # A bare import of every lib module must succeed without a live cluster.
    import lib.ai  # noqa: F401
    import lib.atlas_client  # noqa: F401
    import lib.embeddings  # noqa: F401
    import lib.knowledge  # noqa: F401
    import lib.master_data  # noqa: F401
    import lib.queries  # noqa: F401
    import lib.readiness  # noqa: F401
    import lib.sample_data  # noqa: F401
    import lib.schema  # noqa: F401
    import lib.transactions  # noqa: F401
    import lib.ui  # noqa: F401


def test_builders_are_deterministic_and_consistent():
    products = build_products()
    plots, events, predictions = build_plots_and_events(products)
    assert {p["product_id"] for p in products} == set(PRODUCT_IDS)
    assert {p["plot_id"] for p in plots} == set(PLOT_IDS)
    assert len(predictions) == len(plots)
    assert all(e["product_ref"] in PRODUCT_IDS for e in events)
    assert len(build_crops()) >= 1
    # Snapshot vs resolved field sets are disjoint by design.
    assert not (set(SNAPSHOT_FIELDS) & set(RESOLVED_FIELDS))


def test_pipeline_builds_from_allowlisted_plot_only():
    pipeline = residue_decision_pipeline(PLOT_IDS[0])
    stages = [next(iter(s)) for s in pipeline]
    assert stages[0] == "$match" and "$lookup" in stages and stages[-1] == "$sort"
    assert RELEVANT_INDEXES
    with pytest.raises(ValueError):
        residue_decision_pipeline("PLOT-999")


def test_local_embedder_is_deterministic_and_normalized():
    emb = LocalEmbedder()
    assert emb.dim == embedding_dim()
    texts = [note_text(n) for n in NOTES[:3]]
    v1 = emb.embed_documents(texts)
    v2 = emb.embed_documents(texts)
    assert v1 == v2  # deterministic
    for vec in v1:
        assert len(vec) == emb.dim
        assert abs(_cosine(vec, vec) - 1.0) < 1e-9  # unit vectors


def test_extractive_answer_grounds_in_sources():
    sources = [{"note_id": n["note_id"], "title": n["title"], "body": n["body"]}
               for n in NOTES[:2]]
    answer = _extractive_answer("residue at harvest?", sources)
    assert NOTES[0]["title"] in answer
    assert _extractive_answer("q", []).startswith("No matching guidance")


@pytest.mark.skipif(not ping(), reason="Atlas not reachable")
def test_readiness_runs_when_connected():
    from lib.readiness import run_all

    rows = run_all()
    names = {r["name"] for r in rows}
    assert "MongoDB connectivity" in names
    assert all({"name", "ok", "detail", "fix"} <= set(r) for r in rows)
