"""Smoke tests for Product Catalog Studio.

Offline checks compile every page/script, import every library module, and
exercise the pure builders, the query builders, the local embedder, the fusion
maths, and the extractive summary — so `pytest` passes with no Atlas cluster.
The connectivity-guarded check runs the readiness suite when a cluster is
reachable and skips cleanly otherwise, so tests never fail for environmental
reasons.

Run: python3 -m pytest tests -v
"""

import py_compile
from pathlib import Path

import pytest

from lib.ai import _extractive_summary
from lib.atlas_client import (ALL_CATEGORIES, CATEGORIES, PRODUCT_TYPES,
                              STATUSES, TYPE_ATTRIBUTE, ping)
from lib.catalog import build_filter, validate_product
from lib.embeddings import LocalEmbedder, embedding_dim, product_text
from lib.sample_data import build_products
from lib.search import (FILTER_PATHS, KEYWORD_PATHS, MODES, RRF_K,
                        explain_result, keyword_stage, rrf_fuse,
                        text_index_definition, vector_index_definition,
                        vector_stage)

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
    import lib.catalog  # noqa: F401
    import lib.embeddings  # noqa: F401
    import lib.readiness  # noqa: F401
    import lib.sample_data  # noqa: F401
    import lib.search  # noqa: F401
    import lib.ui  # noqa: F401


def test_catalog_is_deterministic_and_type_consistent():
    first, second = build_products(), build_products()
    assert [d["product_id"] for d in first] == [d["product_id"] for d in second]
    assert len({d["product_id"] for d in first}) == len(first)
    assert len({d["sku"] for d in first}) == len(first)
    for doc in first:
        assert doc["product_type"] in PRODUCT_TYPES
        assert doc["category"] in CATEGORIES[doc["product_type"]]
        assert doc["category"] in ALL_CATEGORIES
        assert doc["status"] in STATUSES
        assert doc["price"]["amount"] > 0
    # Every type is represented, and every status appears somewhere.
    assert {d["product_type"] for d in first} == set(PRODUCT_TYPES)
    assert {d["status"] for d in first} == set(STATUSES)


def test_each_type_carries_its_own_attribute_only():
    docs = build_products()
    for ptype, (path, _label, options) in TYPE_ATTRIBUTE.items():
        parent, child = path.split(".")
        for doc in docs:
            present = child in (doc.get(parent) or {})
            assert present == (doc["product_type"] == ptype)
            if present:
                assert doc[parent][child] in options


def test_build_filter_maps_ui_selections_to_query_document():
    assert build_filter(None) == {}
    query = build_filter({"product_type": "consumable", "category": "Reagents",
                          "status": "active", "price_min": 10, "price_max": 200,
                          "type_attribute": "Flammable"})
    assert query["product_type"] == "consumable"
    assert query["price.amount"] == {"$gte": 10.0, "$lte": 200.0}
    assert query["handling.hazard_class"] == "Flammable"
    # A type attribute without a chosen type is ignored, not misapplied.
    assert build_filter({"type_attribute": "Flammable"}) == {}


def test_validate_product_rejects_bad_payloads():
    good = {"name": "N", "sku": "S", "product_type": "equipment",
            "category": "Measurement", "status": "active",
            "price": {"amount": 1.0}, "summary": "s"}
    assert validate_product(good) == []
    assert validate_product({**good, "name": " "})
    assert validate_product({**good, "category": "Reagents"})  # wrong for type
    assert validate_product({**good, "status": "sold_out"})
    assert validate_product({**good, "price": {"amount": -1}})
    assert validate_product({**good, "summary": ""})


def test_local_embedder_is_deterministic_and_normalized():
    emb = LocalEmbedder()
    assert emb.dim == embedding_dim()
    texts = [product_text(d) for d in build_products()[:3]]
    v1, v2 = emb.embed_documents(texts), emb.embed_documents(texts)
    assert v1 == v2  # deterministic across calls
    for vec in v1:
        assert len(vec) == emb.dim
        assert abs(sum(x * x for x in vec) - 1.0) < 1e-9  # unit vectors


def test_search_stages_carry_index_and_filters():
    filters = {"product_type": "equipment", "type_attribute": "Battery"}
    stage = keyword_stage("balance", filters)["$search"]
    assert stage["compound"]["must"][0]["text"]["path"] == KEYWORD_PATHS
    assert {"equals": {"path": "specs.power_source", "value": "Battery"}} \
        in stage["compound"]["filter"]
    vstage = vector_stage([0.0, 1.0], filters, 5)["$vectorSearch"]
    assert vstage["path"] == "embedding" and vstage["limit"] == 5
    assert vstage["filter"]["specs.power_source"] == "Battery"


def test_index_definitions_cover_every_filter_and_search_path():
    text = text_index_definition()
    fields = text["definition"]["mappings"]["fields"]
    assert text["definition"]["mappings"]["dynamic"] is False
    # The SKU is shown on every product card, so it must be keyword-searchable.
    assert "sku" in KEYWORD_PATHS
    for path in KEYWORD_PATHS:
        assert fields[path] == {"type": "string"}
    for path in FILTER_PATHS:
        if "." in path:
            parent, child = path.split(".")
            assert child in fields[parent]["fields"]
        else:
            assert fields[path]["type"] in ("token", "number")

    vector = vector_index_definition(64)
    vfields = vector["definition"]["fields"]
    assert vfields[0] == {"type": "vector", "path": "embedding",
                          "numDimensions": 64, "similarity": "cosine"}
    assert {f["path"] for f in vfields[1:]} == set(FILTER_PATHS)


def test_rrf_fuse_ranks_documents_present_in_both_legs_first():
    keyword = [{"product_id": "A"}, {"product_id": "B"}]
    semantic = [{"product_id": "C"}, {"product_id": "A"}]
    fused = rrf_fuse(keyword, semantic, limit=3)
    assert [d["product_id"] for d in fused][0] == "A"
    assert fused[0]["keyword_rank"] == 1 and fused[0]["semantic_rank"] == 2
    expected = 1 / (RRF_K + 1) + 1 / (RRF_K + 2)
    assert abs(fused[0]["fused_score"] - expected) < 1e-6


def test_explanations_only_cite_stored_fields():
    doc = build_products()[0] | {"keyword_score": 2.5}
    for mode in MODES:
        text = explain_result(doc, mode, fusion="test fusion")
        assert doc["status"] in text and doc["category"] in text


def test_extractive_summary_grounds_in_retrieved_products():
    docs = build_products()[:2]
    text = _extractive_summary("a mixer", docs)
    assert docs[0]["name"] in text and docs[1]["product_id"] in text
    assert "no shortlist" in _extractive_summary("q", [])


@pytest.mark.skipif(not ping(), reason="Atlas not reachable")
def test_readiness_runs_when_connected():
    from lib.readiness import run_all

    rows = run_all()
    names = {r["name"] for r in rows}
    assert "MongoDB connectivity" in names
    assert all({"name", "ok", "detail", "fix"} <= set(r) for r in rows)
