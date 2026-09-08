"""MongoDB Foundations: Live Walkthrough — landing page.

A presenter-driven, 90-minute foundations session for architects with deep
relational experience. Six independent sections, one dedicated synthetic demo
database, and no automatic writes.

    streamlit run app.py
"""

import streamlit as st

from lib.mongo_client import DB_NAME
from lib.ui import (SUBTITLE, TITLE, page_setup, presenter_mode, prose,
                    sidebar_reset, synthetic_note)

page_setup("Start", icon="🍃")
presenter_mode()
sidebar_reset()

st.markdown("# 🍃 {}".format(TITLE))
st.caption(SUBTITLE)

SECTIONS = [
    ("pages/1_Document_Model.py", "①", "Document model & data modeling",
     "One customer document, the relational-to-document mapping, and the "
     "schema validation rules the server enforces."),
    ("pages/2_Querying_and_Aggregation.py", "②", "Querying & aggregation",
     "A projected find and a $match/$group pipeline, run live."),
    ("pages/3_Indexes_and_Query_Behavior.py", "③", "Indexes & query behaviour",
     "The index list, a compound-index query, and explain execution stats."),
    ("pages/4_Transactions_and_Consistency.py", "④", "Transactions & consistency",
     "An isolated, reversible multi-document transfer between two accounts."),
    ("pages/5_Replica_Sets_and_Scale.py", "⑤", "Replica sets, resilience & scale",
     "A read-only deployment summary and the sharding callout."),
    ("pages/6_Monitoring_Handoff.py", "⑥", "Monitoring handoff",
     "What to inspect in any monitoring tool, then switch to Atlas."),
]

cols = st.columns(3)
for i, (path, number, title, description) in enumerate(SECTIONS):
    with cols[i % 3]:
        with st.container(border=True):
            st.markdown("**{} {}**".format(number, title))
            st.caption(description)
            st.page_link(path, label="Open section →")

st.markdown("---")
st.page_link("pages/7_Demo_Readiness.py",
             label="🩺 Demo Readiness — URI, connection, permissions, seed "
                   "data, indexes, schema validators, and transaction "
                   "availability")

prose(
    "**How this session is built.** Every section stands alone: it checks its "
    "own prerequisites, runs only prebuilt operations, and can be reset. All "
    "reads and writes are confined to the database `{}`. Nothing is written "
    "when the app starts — seeding and the transaction demo are explicit, "
    "confirmed actions.\n\n"
    "**Framing for a relational audience.** The point is not that documents "
    "replace tables. The point is that the unit of storage matches the unit of "
    "access, so the modelling question becomes *what is read and written "
    "together?* Where an invariant genuinely spans documents, MongoDB offers "
    "multi-document ACID transactions — shown in section ④.".format(DB_NAME))

st.markdown("### Running order")
st.markdown(
    "1. **Demo Readiness** — confirm the environment before the audience "
    "arrives.\n"
    "2. **① Document model** → **② Querying & aggregation** → "
    "**③ Indexes & explain** → **④ Transactions** → **⑤ Replica sets** → "
    "**⑥ Monitoring handoff**.\n"
    "3. Switch to Atlas for live metrics at the end.")

st.markdown("---")
synthetic_note()
st.caption("Demo database: `{}`. The app connects only through `MONGODB_URI` "
           "and never creates, modifies, or destroys infrastructure."
           .format(DB_NAME))
