"""Product Catalog Studio — MongoDB 101/201 demo (landing page).

A GUI-first, presenter-ready product catalog for a 60-minute customer session.
Kestrel Labworks is a wholly invented brand and every product, price, and
specification is synthetic.

    streamlit run app.py

Four independent routes: browse and filter the catalog (101), create and edit a
product (101), find the right product with keyword / semantic / hybrid retrieval
(201), and a discovery checklist for the conversation that follows.
"""

import streamlit as st

from lib.atlas_client import BRAND
from lib.ui import connection_guard, synthetic_note

st.set_page_config(page_title="Product Catalog Studio · MongoDB demo",
                   page_icon="🧰", layout="wide")

connection_guard()

st.markdown("# 🧰 Product Catalog Studio")
st.caption(f"A product catalog for {BRAND} — one collection, three product "
           "types, and three ways to search it.")

st.info("**How to use this demo.** Each route below is independent and shows the "
        "exact query it ran against Atlas. Taken left to right, they build the "
        "full story: how the catalog is stored, how it is changed, and how it is "
        "searched.")

st.markdown("### The business problem")
st.markdown(
    "A catalog team sells **instruments, consumables, and service plans**. The "
    "three lines describe themselves with genuinely different attributes: an "
    "instrument has a power source and a lead time, a consumable has a pack "
    "size and a hazard class, a service plan has a response tier and "
    "entitlements. Shoppers then arrive with imprecise wording — *“something to "
    "keep a bath at a steady temperature”* — not with a SKU. Those two facts "
    "drive everything shown here.")

st.markdown("### The routes")
CARDS = [
    ("pages/1_Catalog_Explorer.py", "①", "Catalog explorer",
     "Filter, sort, and page one collection holding three product shapes. (101)"),
    ("pages/2_Product_Editor.py", "②", "Product editor",
     "Create and edit a product, with validation and an audit trail. (101)"),
    ("pages/3_Find_The_Right_Product.py", "③", "Find the right product",
     "Keyword, semantic, and hybrid retrieval side by side. (201)"),
    ("pages/4_Discovery_Checklist.py", "④", "Discovery checklist",
     "The questions to ask next, and the honest limits of this demo."),
]
cols = st.columns(4)
for i, (path, num, title, desc) in enumerate(CARDS):
    with cols[i % 4]:
        with st.container(border=True):
            st.markdown(f"**{num} {title}**")
            st.caption(desc)
            st.page_link(path, label="Open route →")

st.markdown("---")
st.page_link("pages/5_Demo_Readiness.py",
             label="🩺 Demo Readiness — check connectivity, seed, indexes, "
                   "Atlas Search, Vector Search, and optional AI keys")

st.markdown("### What each half shows")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**MongoDB 101 — the document model**")
    st.markdown(
        "- One collection, three product shapes, no sparse columns\n"
        "- Structured filters and sorts as plain query documents\n"
        "- A new attribute needs no migration and no downtime\n"
        "- Application-level validation before the write, plus an audit event")
with c2:
    st.markdown("**MongoDB 201 — search in the same place as the data**")
    st.markdown(
        "- Atlas Search for exact wording (BM25 over name/summary/description)\n"
        "- Atlas Vector Search for intent, over an embedding stored on the "
        "product document itself\n"
        "- Hybrid via `$rankFusion`, with a deterministic in-app RRF fallback\n"
        "- The same structured filters apply to all three modes")

st.markdown("### Honest limits")
st.markdown(
    "- The default embedder is a small deterministic local model, chosen so the "
    "demo runs with **no API keys**. It shows the mechanics of vector search, "
    "not the quality of a production embedding model.\n"
    "- The catalog is 18 products. Relevance behaviour at catalog scale needs a "
    "test on real data.\n"
    "- Where a workload is dominated by rigid relational constraints and heavy "
    "normalized joins, that is a conversation worth having rather than a point "
    "this demo argues away.")

st.markdown("---")
synthetic_note()
st.caption("Runs against an existing MongoDB Atlas cluster. This project never "
           "creates or deletes clusters.")
