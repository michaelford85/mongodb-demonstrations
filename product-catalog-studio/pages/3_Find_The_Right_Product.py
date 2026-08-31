"""Route ③: Find the right product — keyword, semantic, and hybrid retrieval."""

import streamlit as st

from lib.ai import claude_available, summarize_shortlist
from lib.atlas_client import (ALL_CATEGORIES, CATEGORIES, PRODUCT_TYPES,
                              STATUSES, TYPE_LABELS)
from lib.catalog import type_attribute_options
from lib.embeddings import embedding_dim, provider_name
from lib.search import MODES, rerank, rerank_available, run_search
from lib.ui import (MODE_COLOR, badge, connection_guard, page_header,
                    product_card, query_panel, seed_guard, story_arc,
                    synthetic_note)

st.set_page_config(page_title="Product Catalog Studio · Find the right product",
                   page_icon="③", layout="wide")
connection_guard()
seed_guard()

EXAMPLES = [
    "stop my reaction vessel from overheating overnight",
    "EQP-101",
    "I need to weigh samples away from a power socket",
    "protect glassware from corrosive splashes",
    "reduce downtime when an instrument fails on a weekend",
]

page_header("③", "Find the right product",
            "Shoppers describe a problem, not a SKU. Compare exact-wording "
            "search, intent search, and the two fused together.")
story_arc(
    problem="Shoppers describe an outcome in their own words, so exact-term "
            "matching alone misses the product they actually need.",
    interaction="Ask in plain language, then switch retrieval mode and watch the "
                "shortlist change.",
    mechanism="Atlas Search and Atlas Vector Search over the same documents, "
              "fused with `$rankFusion` — no separate search system to sync.",
    tradeoff="The default embedder is a small local model chosen so this runs "
             "with no API keys; relevance quality needs a real-data test.")

query = st.text_input("What do you need?", value=EXAMPLES[0])
cols = st.columns(len(EXAMPLES))
for col, example in zip(cols, EXAMPLES):
    if col.button(example[:26] + "…" if len(example) > 27 else example,
                  use_container_width=True):
        st.session_state.pcs_query = example
        st.rerun()
if st.session_state.get("pcs_query"):
    query = st.session_state.pop("pcs_query")
    st.info(f"Searching for: **{query}**")

st.sidebar.markdown("### Retrieval")
mode = st.sidebar.radio("Mode", MODES, index=2,
                        format_func=lambda m: m.title())
limit = st.sidebar.slider("Results", 3, 10, 5)
st.sidebar.caption(f"Embeddings: `{provider_name()}` · {embedding_dim()} dims")

st.sidebar.markdown("### Same filters as route ①")
ptype = st.sidebar.selectbox("Product type", [None] + PRODUCT_TYPES,
                            format_func=lambda v: "All types" if v is None
                            else TYPE_LABELS[v])
categories = CATEGORIES[ptype] if ptype else ALL_CATEGORIES
category = st.sidebar.selectbox("Category", [None] + categories,
                                format_func=lambda v: v or "All categories")
status = st.sidebar.selectbox("Availability", [None] + STATUSES,
                             format_func=lambda v: (v or "any").title())
attr_label, attr_options = type_attribute_options(ptype)
attr_value = None
if attr_options:
    attr_value = st.sidebar.selectbox(
        attr_label, [None] + attr_options,
        format_func=lambda v: v or f"Any {attr_label.lower()}")

do_rerank = False
if rerank_available():
    do_rerank = st.sidebar.checkbox("Rerank with Voyage AI cross-encoder")
else:
    st.sidebar.caption("Reranking is off — no `VOYAGE_API_KEY` is set. Every "
                       "mode above still works.")

filters = {"product_type": ptype, "category": category, "status": status,
           "type_attribute": attr_value}

if not query.strip():
    st.info("Type a request above, or pick one of the example phrasings.")
    st.stop()

outcome = run_search(query, filters, mode=mode, limit=limit)

st.markdown(badge(f"{mode.title()} retrieval", MODE_COLOR[mode])
            + (" " + badge(outcome["fusion"].replace("`", ""), "#334155")
               if outcome.get("fusion") else ""),
            unsafe_allow_html=True)

if outcome["error"]:
    st.error(outcome["error"]["hint"])
    st.code(outcome["error"]["message"])
    st.stop()

for note in outcome["notes"]:
    st.caption(note)

if not outcome["results"]:
    st.warning("Nothing matched. Try a different phrasing, clear a filter, or "
               "switch to Semantic mode — it does not need shared wording.")
else:
    results = outcome["results"]
    if do_rerank:
        try:
            results = rerank(query, results)
            st.caption("Candidates were retrieved by Atlas, then re-scored by a "
                       "Voyage AI cross-encoder. Original ranks are shown.")
        except Exception as e:  # noqa: BLE001 — never break a live demo
            st.warning(f"Reranking failed, showing retrieval order: {e}")

    for rank, doc in enumerate(results, start=1):
        with st.container(border=True):
            c1, c2 = st.columns([1, 9])
            c1.markdown(f"### #{rank}")
            with c2:
                product_card(doc)
                st.caption(f"🔍 Why this result: {doc.get('explanation', '—')}")

    st.markdown("---")
    st.markdown("#### 🧠 Shortlist summary")
    summary = summarize_shortlist(query, results)
    if summary["mode"] == "claude":
        st.caption(f"Generated by `{summary['model']}` from the retrieved "
                   "products only — retrieval ran first, and the model saw "
                   "nothing else.")
    else:
        st.caption("Extractive summary assembled only from the retrieved product "
                   "fields. No `ANTHROPIC_API_KEY` is set, so no model was "
                   "called.")
    st.info(summary["summary"])
    if summary.get("error"):
        st.warning(f"Claude call failed, fell back to the extractive summary: "
                   f"{summary['error']}")

st.markdown("---")
m1, m2, m3 = st.columns(3)
m1.metric("Results", len(outcome["results"]))
m2.metric("Filter clauses", len(outcome["filters"]))
m3.metric("Retrieval legs", len(outcome["legs"]) or 1)
query_panel("Aggregation pipeline sent to Atlas", outcome["pipeline"])
if not claude_available():
    st.caption("🔐 API keys are optional and read server-side only; none is "
               "required for any retrieval mode on this page.")
synthetic_note()
