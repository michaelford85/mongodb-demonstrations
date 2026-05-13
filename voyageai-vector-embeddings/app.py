import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from search.keyword import keyword_search
from search.semantic import semantic_search
from search.hybrid import hybrid_search
from search.rerank import reranked_search

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Atlas + VoyageAI Product Search",
    page_icon="🛍️",
    layout="wide",
)

# ── Demo content ──────────────────────────────────────────────────────────────

DEMO_QUERIES = [
    "comfortable shoes for walking and standing all day",
    "gift for someone who loves cooking",
    "laptop that won't die on a long flight",
    "noise cancelling headphones for a noisy open office",
    "home office setup for video calls",
    "something to help me sleep better",
    "waterproof jacket for hiking in the rain",
    "affordable robot vacuum for pet hair",
]

MODE_META = {
    "keyword": {
        "label": "🔤 Keyword",
        "tagline": "Traditional BM25 text matching — finds products containing your exact words.",
        "story": (
            "This is how most legacy search works. It matches words literally, so queries like "
            "*\"something to help me sleep better\"* return nothing useful — the words don't appear "
            "in product titles. Great for catalog lookup; poor for intent-driven discovery."
        ),
        "color": "#6b7280",
    },
    "semantic": {
        "label": "🧠 Semantic",
        "tagline": "VoyageAI voyage-3.5 understands meaning, not just words.",
        "story": (
            "Your query is converted into a 1,024-dimension vector that captures intent. "
            "MongoDB Atlas finds the closest products by meaning — so *\"comfortable shoes for "
            "long walks\"* surfaces trail runners and orthopedic insoles even if neither phrase "
            "appears in those product descriptions."
        ),
        "color": "#2563eb",
    },
    "hybrid": {
        "label": "⚡ Hybrid",
        "tagline": "Reciprocal Rank Fusion combines semantic depth with keyword precision.",
        "story": (
            "Hybrid search runs both pipelines and merges results using RRF scoring. "
            "Brand and model queries (*\"Sony WH-1000XM5 alternatives\"*) stay precise "
            "while open-ended discovery queries stay smart. Best of both worlds."
        ),
        "color": "#7c3aed",
    },
    "rerank": {
        "label": "🎯 + Rerank",
        "tagline": "VoyageAI voyage-rerank-2 re-scores results so the best match is always #1.",
        "story": (
            "The reranker evaluates how relevant each candidate is to the full query intent — "
            "not just similarity scores. It reshuffles the hybrid results so the most relevant "
            "product leads, every time. Watch the rank-change badges to see it in action."
        ),
        "color": "#059669",
    },
}

# ── Cached search functions ───────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def run_keyword(query: str, limit: int):
    return keyword_search(query, limit)

@st.cache_data(ttl=300, show_spinner=False)
def run_semantic(query: str, limit: int):
    return semantic_search(query, limit)

@st.cache_data(ttl=300, show_spinner=False)
def run_hybrid(query: str, limit: int):
    return hybrid_search(query, limit)

@st.cache_data(ttl=300, show_spinner=False)
def run_reranked(query: str, limit: int):
    return reranked_search(query, limit)

# ── UI helpers ────────────────────────────────────────────────────────────────

def star_rating(rating) -> str:
    if not rating:
        return ""
    filled = round(rating)
    return "★" * filled + "☆" * (5 - filled) + f" {rating:.1f}"


def price_str(price) -> str:
    if price is None:
        return ""
    return f"${price:.2f}"


def render_product_card(product: dict, rank: int, show_rerank_badge: bool = False):
    with st.container(border=True):
        col_img, col_info = st.columns([1, 4], gap="medium")

        with col_img:
            img = product.get("image_url")
            if img:
                try:
                    st.image(img, width=110)
                except Exception:
                    st.markdown("📦", help="Image unavailable")
            else:
                st.markdown("📦")

        with col_info:
            title = product.get("title", "Untitled")
            st.markdown(f"**{rank}. {title}**")

            meta_parts = []
            if product.get("category"):
                meta_parts.append(f"`{product['category']}`")
            stars = star_rating(product.get("rating"))
            if stars:
                n = product.get("rating_count")
                rating_str = stars + (f" ({n:,})" if n else "")
                meta_parts.append(rating_str)
            p = price_str(product.get("price"))
            if p:
                meta_parts.append(f"**{p}**")
            if meta_parts:
                st.markdown("  ·  ".join(meta_parts))

            desc = product.get("description", "")
            if desc:
                st.caption(desc[:280] + "…" if len(desc) > 280 else desc)

            # Rerank rank-change badge
            if show_rerank_badge:
                orig = product.get("original_hybrid_rank")
                if orig and orig != rank:
                    direction = "⬆" if orig > rank else "⬇"
                    delta = abs(orig - rank)
                    badge_color = "green" if orig > rank else "orange"
                    st.markdown(
                        f"<span style='color:{badge_color};font-size:0.8em'>"
                        f"{direction} Moved {delta} spot{'s' if delta > 1 else ''} "
                        f"(was #{orig} in hybrid)</span>",
                        unsafe_allow_html=True,
                    )


def render_results(results: list[dict], debug: dict, mode: str, query: str):
    meta = MODE_META[mode]

    st.markdown(f"##### {meta['tagline']}")
    with st.expander("What's happening here?", expanded=False):
        st.markdown(meta["story"])

    st.markdown("---")

    if not results:
        st.warning(
            "No results returned. Make sure the Atlas indexes are active and "
            "products have been loaded. See the README for setup steps."
        )
        return

    st.markdown(f"**Top {len(results)} results for:** _{query}_")
    st.markdown("")

    show_badges = mode == "rerank"
    for i, product in enumerate(results, 1):
        render_product_card(product, i, show_rerank_badge=show_badges)

    with st.expander("🔧 Under the Hood", expanded=False):
        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown("**Pipeline**")
            for stage in debug.get("pipeline_stages", []):
                st.markdown(f"- `{stage}`")
            st.markdown("")
            st.markdown("**Index / Model**")
            for k in ("vector_index", "text_index", "index", "embedding_model",
                      "rerank_model", "similarity", "rrf_k", "approach",
                      "embedding_dimensions", "candidates_fetched"):
                if k in debug:
                    label = k.replace("_", " ").title()
                    st.markdown(f"- **{label}:** `{debug[k]}`")

        with col_r:
            st.markdown("**Score Breakdown (top 5)**")
            for i, product in enumerate(results[:5], 1):
                breakdown = product.get("score_breakdown", {})
                if breakdown:
                    st.markdown(f"**{i}. {product.get('title', '')[:40]}…**")
                    for k, v in breakdown.items():
                        st.markdown(f"  - {k}: `{v}`")


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ Settings")
    n_results = st.slider("Results per search", min_value=5, max_value=20, value=10)
    st.markdown("---")
    st.markdown("## How this demo works")
    st.markdown(
        "Each tab runs the same query through a different search strategy. "
        "Try a natural-language query to see where keyword search falls short "
        "and how semantic understanding + reranking fill the gap."
    )
    st.markdown("---")
    st.markdown("**Stack**")
    st.markdown(
        f"- MongoDB Atlas Vector Search\n"
        f"- Atlas Search (BM25)\n"
        f"- VoyageAI `{os.getenv('VOYAGE_MODEL', 'voyage-3.5')}`\n"
        f"- VoyageAI `{os.getenv('VOYAGE_RERANK_MODEL', 'voyage-rerank-2')}`"
    )

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("# 🛍️ Product Search Demo")
st.markdown(
    "**MongoDB Atlas Vector Search + VoyageAI** — "
    "showing how AI-native search turns intent into revenue."
)
st.markdown("---")

# ── Search input ──────────────────────────────────────────────────────────────

col_select, col_custom, col_btn = st.columns([2, 2, 1], gap="small")

with col_select:
    selected = st.selectbox(
        "Demo query",
        DEMO_QUERIES,
        key="demo_query_select",
        label_visibility="collapsed",
    )

with col_custom:
    custom = st.text_input(
        "Custom query",
        placeholder="Or type your own query here…",
        key="custom_query_input",
        label_visibility="collapsed",
    )

with col_btn:
    search_clicked = st.button("🔍 Search", use_container_width=True, type="primary")

active_query = custom.strip() if custom.strip() else selected

if search_clicked:
    st.session_state["active_query"] = active_query
    st.session_state["n_results"] = n_results

stored_query = st.session_state.get("active_query")
stored_limit = st.session_state.get("n_results", n_results)

# ── Results tabs ──────────────────────────────────────────────────────────────

if not stored_query:
    st.markdown("")
    st.info(
        "Choose a demo query from the dropdown above (or type your own) and click **Search** "
        "to see all four search strategies side-by-side."
    )
    with st.expander("Suggested queries to try"):
        for q in DEMO_QUERIES:
            st.markdown(f"- _{q}_")
else:
    tab_kw, tab_sem, tab_hyb, tab_rerank = st.tabs([
        MODE_META["keyword"]["label"],
        MODE_META["semantic"]["label"],
        MODE_META["hybrid"]["label"],
        MODE_META["rerank"]["label"],
    ])

    with tab_kw:
        with st.spinner("Searching…"):
            kw_results, kw_debug = run_keyword(stored_query, stored_limit)
        render_results(kw_results, kw_debug, "keyword", stored_query)

    with tab_sem:
        with st.spinner("Embedding query and searching…"):
            sem_results, sem_debug = run_semantic(stored_query, stored_limit)
        render_results(sem_results, sem_debug, "semantic", stored_query)

    with tab_hyb:
        with st.spinner("Running hybrid search…"):
            hyb_results, hyb_debug = run_hybrid(stored_query, stored_limit)
        render_results(hyb_results, hyb_debug, "hybrid", stored_query)

    with tab_rerank:
        with st.spinner("Fetching candidates and reranking…"):
            rerank_results, rerank_debug = run_reranked(stored_query, stored_limit)
        render_results(rerank_results, rerank_debug, "rerank", stored_query)
