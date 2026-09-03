"""Route ①: Data model & schema validation."""

from datetime import datetime, timezone

import streamlit as st
from pymongo.errors import WriteError

from lib.atlas_client import PLOT_IDS
from lib.schema import ALLOWED_RISK_LEVELS, apply_validators, get_validator_info
from lib.ui import (badge, connection_guard, db, page_header, presenter_notes,
                    seed_guard, story_arc, synthetic_note)

st.set_page_config(page_title="CropTrace · Data model & validation",
                   page_icon="①", layout="wide")
connection_guard()
seed_guard()
database = db()

page_header("①", "Data model & schema validation",
            "An embedded plot document for data read together, an authoritative "
            "product collection, and a governed JSON Schema on top.")
story_arc(
    problem="A plot's plan, weather, and prediction are almost always read "
            "together; product master data is read everywhere and changes often.",
    interaction="Inspect a plot document, inspect the product collection, then "
                "try an invalid and a valid write.",
    mechanism="Embedded arrays for locality + a `$jsonSchema` validator with "
              "required fields, types, and allowed statuses.",
    tradeoff="If the plan/weather/prediction were queried mostly independently "
             "and joined ad-hoc, a normalized relational model could fit better.")

presenter_notes(
    talk_track="CropTrace reads a plot with its treatments, recent weather, and "
               "the latest residue prediction as one unit — so we embed them, "
               "and Atlas returns the whole view in a single read. Product "
               "master data lives in its own authoritative collection because "
               "it changes often and is shared. Flexible schema does not mean "
               "no schema: a JSON Schema validator enforces required fields, "
               "BSON types, and allowed statuses, rejecting bad writes.",
    click_path=["Expand the plot document inspector",
                "Show the separate crop_protection_products collection",
                "Read the active validator",
                "Click 'Attempt invalid write' → see it rejected",
                "Click 'Attempt valid write' → see it succeed"],
    takeaway="Document locality for read-together data, with server-side schema "
             "governance via $jsonSchema.",
    caveat="When many entities are queried independently and joined in every "
           "query, a normalized relational schema may be the cleaner fit.")

left, right = st.columns(2, gap="large")
with left:
    st.markdown("#### 🧾 Plot document (embedded, read together)")
    plot_id = st.selectbox("Plot", PLOT_IDS)
    plot = database.plots.find_one({"plot_id": plot_id}, {"_id": 0})
    st.caption("`treatments`, `weather_observations`, and `residue_prediction` "
               "are embedded — one read returns the whole plot view.")
    st.json(plot, expanded=False)
with right:
    st.markdown("#### 📚 crop_protection_products (authoritative master data)")
    st.caption("A separate collection for frequently-updated, shared master "
               "data — referenced by treatments, not copied into them.")
    st.json(list(database.crop_protection_products.find({}, {"_id": 0}).limit(3)),
            expanded=False)

st.markdown("---")
st.markdown("#### 🛡️ Active JSON Schema validator")
vcoll = st.selectbox("Validated collection",
                     ["plots", "crop_protection_products", "treatment_events"])
info = get_validator_info(database, vcoll)
if info.get("validator"):
    m1, m2 = st.columns(2)
    m1.metric("validationLevel", info.get("validationLevel", "-"))
    m2.metric("validationAction", info.get("validationAction", "-"))
    st.json(info["validator"], expanded=False)
else:
    st.warning("No validator found on this collection. Use **Reset** below to "
               "re-apply validators.")
st.markdown("Allowed risk levels (reference): "
            + " ".join(badge(r, "#2563eb") for r in ALLOWED_RISK_LEVELS),
            unsafe_allow_html=True)

st.markdown("---")
st.markdown("#### ✍️ Prove the validator (safe writes to `treatment_events`)")
st.caption("The invalid write is rejected by Atlas; the valid write is inserted "
           "and then removed so the demo stays clean.")
c1, c2 = st.columns(2)
with c1:
    if st.button("🚫 Attempt invalid write", use_container_width=True):
        bad = {"treatment_id": "TRT-DEMO-BAD", "plot_id": "PLOT-001",
               "product_ref": "CPP-001", "status": "not_a_status"}
        try:
            database.treatment_events.insert_one(bad)
            st.error("Unexpected: invalid write was accepted.")
            database.treatment_events.delete_one({"treatment_id": "TRT-DEMO-BAD"})
        except WriteError as e:
            st.error("Rejected by the validator (as intended).")
            st.caption("`status: 'not_a_status'` is not in the allowed enum.")
            st.code(str(e.details or e), language="json")
with c2:
    if st.button("✅ Attempt valid write", type="primary",
                 use_container_width=True):
        tid = "TRT-DEMO-OK-" + datetime.now(timezone.utc).strftime("%H%M%S%f")
        good = {"treatment_id": tid, "plot_id": "PLOT-001",
                "product_ref": "CPP-001", "status": "planned",
                "dose_l_per_ha": 0.8}
        try:
            database.treatment_events.insert_one(good)
            st.success(f"Accepted and inserted `{tid}`.")
            database.treatment_events.delete_one({"treatment_id": tid})
            st.caption("Removed again to keep the demo data deterministic.")
        except WriteError as e:
            st.error(f"Unexpected rejection: {e}")

st.markdown("---")
if st.button("🔄 Reset demo (re-apply validators & clear demo writes)"):
    apply_validators(database)
    database.treatment_events.delete_many(
        {"treatment_id": {"$regex": "^TRT-DEMO"}})
    st.toast("Validators re-applied and demo writes cleared.")
    st.rerun()
synthetic_note()
