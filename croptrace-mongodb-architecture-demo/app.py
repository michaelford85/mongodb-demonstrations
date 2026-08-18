"""CropTrace — MongoDB Atlas architecture demo (landing page).

A GUI-first, presenter-ready story for evaluating a migration of remaining
CropTrace application components (currently on DynamoDB, weighed against Aurora
PostgreSQL) onto MongoDB Atlas. Six independent demo routes each stand alone.

    streamlit run app.py

This is a technical demonstration, not a production system. All data is
synthetic. The framing is deliberately even-handed: MongoDB strengths are
presented as design/operational trade-offs for *this* workload, and each route
names where a relational design may be the better fit.
"""

import streamlit as st

from lib.ui import connection_guard, synthetic_note

st.set_page_config(page_title="CropTrace · MongoDB Atlas architecture demo",
                   page_icon="🌱", layout="wide")

connection_guard()

st.markdown("# 🌱 CropTrace on MongoDB Atlas")
st.caption("Residue-risk prediction for fruit & vegetable growers — an "
           "architecture story for a DynamoDB → MongoDB migration, evaluated "
           "alongside Aurora PostgreSQL.")

st.info("**How to use this demo.** Every route below is independent: it has its "
        "own setup check, presenter notes, and reset. A presenter can cover one "
        "topic, or hand a single topic to a colleague. Start with **Demo "
        "Readiness** to confirm the environment is ready.")

st.markdown("### The workload")
st.markdown(
    "CropTrace combines **treatment plans, weather, crop-protection-product "
    "data, and crop/plot information** to predict residue risk at harvest. The "
    "data for a single plot is largely *read together*, master product data "
    "changes often and must stay authoritative, and a few operations need "
    "cross-collection joins or atomic multi-document writes. Those access "
    "patterns drive the design choices shown here.")

st.markdown("### The six routes")
CARDS = [
    ("pages/1_Data_Model_and_Validation.py", "①", "Data model & schema validation",
     "Embedded plot documents + a governed JSON Schema. Flexible ≠ uncontrolled."),
    ("pages/2_Master_Data_and_Duplication.py", "②", "Master data & controlled duplication",
     "Display snapshot vs authoritative reference for frequently-changing products."),
    ("pages/3_Aggregation_and_Lookup.py", "③", "Aggregation & $lookup",
     "A real decision pipeline with $match/$lookup/$project + explain plan."),
    ("pages/4_ACID_Transactions.py", "④", "ACID transaction scenario",
     "A multi-document transaction with a safe simulated-failure rollback."),
    ("pages/5_Seasonal_Scale.py", "⑤", "Seasonal scale & operations",
     "Synthetic seasonal demand + an Atlas-vs-Aurora sizing checklist."),
    ("pages/6_Knowledge_Assistant.py", "⑥", "AI: Voyage + Vector Search + Claude",
     "Retrieval-first grounded assistant. Runs with no keys, too."),
]
cols = st.columns(3)
for i, (path, num, title, desc) in enumerate(CARDS):
    with cols[i % 3]:
        with st.container(border=True):
            st.markdown(f"**{num} {title}**")
            st.caption(desc)
            st.page_link(path, label="Open route →")

st.markdown("---")
st.page_link("pages/7_Demo_Readiness.py",
             label="🩺 Demo Readiness — check connectivity, seed, validators, "
                   "indexes, vector search, and optional AI keys")

st.markdown("### The even-handed frame")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Where MongoDB fits this workload**")
    st.markdown(
        "- Document locality for data read together (a plot and its plan)\n"
        "- Flexible but **governed** schema evolution (JSON Schema validators)\n"
        "- Targeted denormalization with a single source of truth\n"
        "- Aggregation + `$lookup` when relationships must be resolved\n"
        "- Multi-document transactions when writes must be atomic\n"
        "- Atlas operational automation + integrated search / vector search")
with c2:
    st.markdown("**Where PostgreSQL may be the better fit**")
    st.markdown(
        "- Rigid relational constraints and heavy normalized joins dominate\n"
        "- Strong foreign-key / referential-integrity enforcement is required\n"
        "- The team's tooling and expertise are deeply relational\n"
        "- Reporting is primarily ad-hoc SQL across many normalized tables\n\n"
        "This demo does **not** claim MongoDB universally replaces relational "
        "databases. It shows the design choice *in the context of CropTrace's "
        "access patterns*.")

st.markdown("---")
synthetic_note()
st.caption("Uses the Atlas cluster from `atlas-cluster-provisioning`. This "
           "project never creates clusters or invokes Terraform.")
