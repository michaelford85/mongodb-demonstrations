"""Data-model and JSON Schema validation tests.

Offline tests check the synthetic data builders and validator documents. The
Atlas-backed test applies a validator to a throwaway collection and proves an
invalid write is rejected while a valid write succeeds — it skips cleanly when
no cluster is reachable so it never fails for environmental reasons.
"""

import pytest
from pymongo.errors import WriteError

from lib.atlas_client import PLOT_IDS, PRODUCT_IDS, ping
from lib.sample_data import build_plots_and_events, build_products
from lib.schema import PLOT_VALIDATOR, VALIDATORS


def test_products_match_allowlist_and_required_fields():
    products = build_products()
    assert {p["product_id"] for p in products} == set(PRODUCT_IDS)
    for p in products:
        assert p["status"] in {"active", "restricted", "withdrawn"}
        assert p["version"] >= 1
        assert p["category"]


def test_plots_embed_read_together_data():
    products = build_products()
    plots, events, predictions = build_plots_and_events(products)
    assert {p["plot_id"] for p in plots} == set(PLOT_IDS)
    for plot in plots:
        assert "treatments" in plot and isinstance(plot["treatments"], list)
        assert "weather_observations" in plot
        assert plot["residue_prediction"]["mrl_mg_kg"] > 0
    # Every treatment event references an allowlisted product.
    assert all(e["product_ref"] in PRODUCT_IDS for e in events)
    assert len(predictions) == len(plots)


def test_validators_are_wellformed():
    for name, opts in VALIDATORS.items():
        assert "$jsonSchema" in opts["validator"]
        assert opts["validationAction"] in {"error", "warn"}
        assert opts["validationLevel"] in {"strict", "moderate", "off"}
    required = PLOT_VALIDATOR["$jsonSchema"]["required"]
    assert "plot_id" in required and "grower_id" in required


@pytest.mark.skipif(not ping(), reason="Atlas not reachable")
def test_invalid_write_rejected_valid_write_accepted():
    from lib.atlas_client import get_db

    db = get_db()
    coll_name = "test_validation_scratch"
    db[coll_name].drop()
    db.create_collection(
        coll_name,
        validator=VALIDATORS["treatment_events"]["validator"],
        validationLevel="strict", validationAction="error")
    try:
        with pytest.raises(WriteError):
            db[coll_name].insert_one({
                "treatment_id": "T1", "plot_id": "PLOT-001",
                "product_ref": "CPP-001", "status": "not_a_status"})
        ok = db[coll_name].insert_one({
            "treatment_id": "T2", "plot_id": "PLOT-001",
            "product_ref": "CPP-001", "status": "planned"})
        assert ok.inserted_id is not None
    finally:
        db[coll_name].drop()
