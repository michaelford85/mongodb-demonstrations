"""Hybrid Search Lab — a GUI that shows results AND the query behind them.

Run each strategy on the same query, compare the rankings, and copy the
exact mongosh aggregation into your own shell to follow along in the cluster.
"""
import streamlit as st

from lib.client import (
    DB_NAME, COLLECTION_NAME, VECTOR_INDEX, TEXT_INDEX, EMBEDDING_MODEL,
    VOYAGE_RERANK_MODEL,
)
from lib.search import (
    keyword_search, semantic_search, hybrid_search, rerank_search,
    RERANK_FETCH_FACTOR,
)
from lib.explain import to_mongosh, stage_notes

st.set_page_config(page_title="Hybrid Search Lab", page_icon="🔎", layout="wide")

DEMO_QUERIES = [
    "a story about overcoming loneliness",
    "something that will make me laugh",
    "people fighting to keep the lights on",
    "a journey across a dangerous landscape",
    "food brings a family back together",
    "uncovering a crime and doing the right thing",
]

MODES = {
    "keyword": ("🔤 Keyword (BM25)", keyword_search,
                "Matches the literal words in your query. Fast and precise for "
                "exact phrasing — but blind to meaning."),
    "semantic": ("🧠 Semantic (autoEmbed)", semantic_search,
                 "Atlas embeds your query with Voyage AI and finds plots with "
                 "similar meaning, even when no words overlap."),
    "hybrid": ("⚡ Hybrid ($rankFusion)", hybrid_search,
               "Fuses the keyword and semantic rankings so exact matches and "
               "intent matches both surface."),
    "rerank": ("🎯 Reranked (Voyage cross-encoder)", rerank_search,
               "Hybrid retrieves a wide candidate set, then a Voyage AI "
               "cross-encoder re-scores each one against the query so the best "
               "match lands first. Runs client-side — needs VOYAGE_API_KEY."),
}


@st.cache_data(ttl=300, show_spinner=False)
def run(mode: str, query: str, limit: int):
    _, fn, _ = MODES[mode]
    results, pipeline = fn(query, limit)
    return results, pipeline


def render_results(results: list):
    if not results:
        st.warning("No results. Confirm both indexes are READY "
                   "(`python scripts/status.py`).")
        return
    for i, doc in enumerate(results, 1):
        with st.container(border=True):
            genres = ", ".join(doc.get("genres", []))
            st.markdown(f"**{i}. {doc.get('title')}**  ·  {doc.get('year')}  ·  `{genres}`")
            st.caption(doc.get("plot", ""))
            score = doc.get("score")
            if score is not None:
                label = "rerank score" if "rerank_rank" in doc else "score"
                meta = f"{label}: {score:.4f}"
                if "hybrid_rank" in doc:
                    meta += (f"  ·  hybrid #{doc['hybrid_rank']} "
                             f"→ rerank #{doc['rerank_rank']}")
                st.markdown(f"<span style='color:#6b7280;font-size:0.8em'>"
                            f"{meta}</span>", unsafe_allow_html=True)


def render_under_hood(pipeline: list):
    st.markdown("##### 🖥️ Run this yourself in mongosh")
    st.caption("Connect with `mongosh \"$MONGODB_URI\"`, then paste:")
    st.code(to_mongosh(pipeline), language="javascript")
    st.markdown("##### 🔧 What each stage does")
    for op, note in stage_notes(pipeline):
        st.markdown(f"- **`{op}`** — {note}")


RERANK_PYTHON = '''import voyageai
voyage = voyageai.Client()  # reads VOYAGE_API_KEY from the environment

# `candidates` are the plots returned by the hybrid query above
reranked = voyage.rerank(
    query=query,
    documents=[c["plot"] for c in candidates],
    model="{model}",
    top_k=5,
)
for item in reranked.results:
    print(round(item.relevance_score, 4), candidates[item.index]["title"])'''


def render_rerank_under_hood(pipeline: list):
    st.markdown("##### 🖥️ Stage 1 — retrieve candidates (reproduce in mongosh)")
    st.caption(f"Hybrid search fetches {RERANK_FETCH_FACTOR}× the requested "
               "results as candidates. This retrieval half is pure Atlas:")
    st.code(to_mongosh(pipeline), language="javascript")
    st.markdown("##### 🧮 Stage 2 — rerank (client-side, not in mongosh)")
    st.caption("A Voyage AI cross-encoder scores each candidate against the query "
               "directly, then keeps the top matches. This calls the Voyage API, "
               "so unlike the other tabs it cannot run in the shell:")
    st.code(RERANK_PYTHON.format(model=VOYAGE_RERANK_MODEL), language="python")


# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔎 Hybrid Search Lab")
    st.markdown("Compare keyword, semantic, and hybrid search on the same query — "
                "then reproduce every result in mongosh.")
    st.markdown("---")
    n = st.slider("Results per strategy", 3, 10, 5)
    st.markdown("---")
    st.markdown("**Cluster namespace**")
    st.markdown(f"- db: `{DB_NAME}`\n- collection: `{COLLECTION_NAME}`")
    st.markdown("**Indexes**")
    st.markdown(f"- vector (autoEmbed): `{VECTOR_INDEX}`\n- text (BM25): `{TEXT_INDEX}`")
    st.markdown(f"- model: `{EMBEDDING_MODEL}`")
    st.markdown(f"- rerank: `{VOYAGE_RERANK_MODEL}`")

# ── Header + query ──────────────────────────────────────────────────────────
st.markdown("# 🔎 Hybrid Search Lab")
st.markdown("Type an **intent-based** query (describe a plot, don't name it). "
            "Keyword search will often miss it — watch semantic and hybrid catch it.")

col_q, col_btn = st.columns([4, 1])
with col_q:
    selected = st.selectbox("Demo query", DEMO_QUERIES, label_visibility="collapsed")
    custom = st.text_input("Custom query", placeholder="…or type your own",
                           label_visibility="collapsed")
with col_btn:
    go = st.button("Search", type="primary", use_container_width=True)

query = custom.strip() or selected

if go:
    st.session_state["q"] = query
    st.session_state["n"] = n

q = st.session_state.get("q")
limit = st.session_state.get("n", n)

if not q:
    st.info("Pick a demo query (or type your own) and click **Search**.")
else:
    st.markdown(f"**Query:** _{q}_")
    tabs = st.tabs([MODES[m][0] for m in MODES])
    for tab, mode in zip(tabs, MODES):
        with tab:
            st.markdown(f"_{MODES[mode][2]}_")
            try:
                with st.spinner("Querying Atlas…"):
                    results, pipeline = run(mode, q, limit)
            except Exception as exc:
                st.error(str(exc))
                continue
            left, right = st.columns([3, 2], gap="large")
            with left:
                render_results(results)
            with right:
                if mode == "rerank":
                    render_rerank_under_hood(pipeline)
                else:
                    render_under_hood(pipeline)
