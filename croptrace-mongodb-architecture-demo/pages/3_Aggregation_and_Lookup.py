"""Route ③: Aggregation & $lookup."""

import json

import pandas as pd
import streamlit as st

from lib.queries import (document_local_view, explain_pipeline, list_plots,
                         residue_decision_pipeline, run_aggregation)
from lib.ui import (connection_guard, db, page_header, presenter_notes,
                    seed_guard, story_arc, synthetic_note)

st.set_page_config(page_title="CropTrace · Aggregation & $lookup",
                   page_icon="③", layout="wide")
connection_guard()
seed_guard()
database = db()

page_header("③", "Aggregation & $lookup",
            "A real decision query: for a selected plot, planned treatments "
            "joined to current product guidance and the residue prediction.")
story_arc(
    problem="A grower decision needs planned treatments, the *current* product "
            "guidance, and the plot's residue prediction together.",
    interaction="Pick a plot, run the pipeline, inspect rows, timing, indexes, "
                "and the explain plan; then contrast a document-local read.",
    mechanism="`$match` → `$lookup` (products, predictions) → `$unwind` → "
              "`$project` → `$sort`, backed by supporting indexes.",
    tradeoff="Join-heavy, highly-normalized reporting across many tables is a "
             "classic relational strength — `$lookup` fits targeted joins, not "
             "every query.")

presenter_notes(
    talk_track="This is the cross-collection pattern. Treatments, products, and "
               "predictions are separate collections because products are "
               "authoritative master data. For this decision we $match the "
               "plot's planned treatments, $lookup the current product record "
               "and the residue prediction, project a tidy row, and sort by "
               "predicted residue. It runs against Atlas, and I can show the "
               "explain plan and the indexes it uses. Then compare a "
               "document-local read of the same plot — different access "
               "pattern, not a universal winner.",
    click_path=["Pick a plot", "Run the pipeline", "Read rows + elapsed time",
                "Open the explain plan", "Compare the document-local read"],
    takeaway="`$lookup` resolves relationships against a single source of truth "
             "when the access pattern is cross-collection.",
    caveat="If most queries join many normalized tables, a relational engine's "
           "join planner and constraints may serve better.")

plots = list_plots(database)
labels = {f"{p['plot_id']} · {p['crop']} ({p['region']})": p["plot_id"]
          for p in plots}
chosen = st.selectbox("Plot", list(labels.keys()))
plot_id = labels[chosen]

st.markdown("#### 🧩 Pipeline")
pipeline = residue_decision_pipeline(plot_id)
st.code(json.dumps(pipeline, indent=2, default=str), language="json")

if st.button("▶️ Run aggregation against Atlas", type="primary"):
    result = run_aggregation(database, plot_id)
    m1, m2, m3 = st.columns(3)
    m1.metric("Result rows", len(result["rows"]))
    m2.metric("Elapsed (live query)", f"{result['elapsed_ms']} ms")
    m3.metric("Stages", len(result["pipeline"]))
    st.caption("⏱️ Elapsed time is a live measurement of this query.")
    if result["rows"]:
        st.dataframe(pd.DataFrame(result["rows"]), use_container_width=True,
                     hide_index=True)
    else:
        st.info("No planned treatments for this plot — pick another.")
    st.markdown("**Relevant indexes**")
    for ix in result["indexes"]:
        st.markdown(f"- `{ix}`")

with st.expander("🔬 Explain plan (guarded — allowlisted plots only)"):
    if st.button("Run explain (queryPlanner)"):
        try:
            plan = explain_pipeline(database, plot_id)
            st.json(plan, expanded=False)
        except Exception as e:  # noqa: BLE001
            st.error(f"Explain unavailable: {e}")

st.markdown("---")
st.markdown("#### 🆚 Document-local read (data accessed together)")
st.caption("The same plot rendered from the embedded `plots` document — no "
           "join. Different access pattern; not claimed to be always faster.")
if st.button("Read plot document locally"):
    local = document_local_view(database, plot_id)
    st.metric("Elapsed (live query)", f"{local['elapsed_ms']} ms")
    st.json(local["plot"], expanded=False)

st.markdown("---")
if st.button("🔄 Reset demo (read-only route — just refresh)"):
    st.rerun()
synthetic_note()
