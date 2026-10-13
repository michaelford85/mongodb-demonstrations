"""MongoDB Foundations: Live Walkthrough — landing page.

A presenter-driven, 90-minute foundations session for architects with deep
relational experience. Seven independent sections, one dedicated synthetic demo
database, and no automatic writes.

The dataset and vocabulary are deliberately industry-neutral, and every named
entity is invented, so the material applies to any vertical.

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
    ("pages/5_Replica_Sets_Overview.py", "⑤", "Replica sets — an overview",
     "Replica-set vocabulary in relational terms, a read-only deployment "
     "summary, and the sharding callout."),
    ("pages/6_High_Availability.py", "⑥", "High availability & MongoDB",
     "Elections, write concern, read preference, retryable writes, and what "
     "the application sees during a failover."),
    ("pages/7_Monitoring_Handoff.py", "⑦", "Monitoring handoff",
     "What to inspect in any monitoring tool, then switch to Atlas."),
    ("pages/9_MongoDB_Search.py", "⑧", "MongoDB Search",
     "One query, four strategies over a chunked corpus: full-text (BM25), "
     "semantic (autoEmbed vector), hybrid ($rankFusion), and AI reranking."),
    ("pages/10_Search_for_RAG.py", "⑨", "Search for RAG",
     "MongoDB as the retrieval half of RAG: a question becomes grounding, then "
     "a prompt, then an optional generated, citeable answer."),
]

cols = st.columns(3)
for i, (path, number, title, description) in enumerate(SECTIONS):
    with cols[i % 3]:
        with st.container(border=True):
            st.markdown("**{} {}**".format(number, title))
            st.caption(description)
            st.page_link(path, label="Open section →")

st.markdown("---")
st.page_link("pages/8_Demo_Readiness.py",
             label="🩺 Demo Readiness — URI, connection, permissions, seed "
                   "data, indexes, schema validators, and transaction "
                   "availability")

prose(
    "**Sections ⑧–⑨ are an optional Search & AI add-on.** The core foundations "
    "session is ①–⑦. The two search sections stand alone, use one extra "
    "collection (`knowledge_chunks`) in the same demo database, and have their "
    "own seed and indexes — `python3 seed_search.py` then "
    "`python3 scripts/create_search_indexes.py`. Semantic search and RAG rely "
    "on Atlas Automated Embedding (a Voyage AI model); the reranker and the RAG "
    "answer step are optional and key-gated, so full-text, semantic, and hybrid "
    "search all run with no extra keys.")

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
    "multi-document ACID transactions — shown in section ④.\n\n"
    "**Industry-agnostic by design.** The data is a set of customers, the "
    "accounts they hold, and a ledger of dated, categorised entries. That shape "
    "recurs in every vertical, so no example depends on one. Every name is "
    "invented: no real organisation is referenced anywhere in the demo."
    .format(DB_NAME))

st.markdown("### Running order")
st.markdown(
    "1. **Demo Readiness** — confirm the environment before the audience "
    "arrives.\n"
    "2. **① Document model** → **② Querying & aggregation** → "
    "**③ Indexes & explain** → **④ Transactions** → **⑤ Replica sets** → "
    "**⑥ High availability** → **⑦ Monitoring handoff**.\n"
    "3. Switch to Atlas for live metrics at the end.")

st.markdown("---")
synthetic_note()
st.caption("Demo database: `{}`. The app connects only through `MONGODB_URI` "
           "and never creates, modifies, or destroys infrastructure."
           .format(DB_NAME))
