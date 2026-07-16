"""Field Advisor — a Grower Assistant powered by MongoDB Atlas.

A GUI-first field demo for an agriculture grower-advisory experience. The same
Atlas backend powers operational records (growers, fields, support cases) and
semantic retrieval (vector search over an agronomy knowledge base). Run the
seed + index scripts first, then:

    streamlit run app.py

This is an illustrative field demo, not a production advisory system. All data
is synthetic and all product/company names are invented for the demo.
"""

import pandas as pd
import streamlit as st

from lib.atlas_client import (CROPS, PRODUCT_LINES, REGIONS, SEASONS,
                              SEVERITIES, db_name, get_db, is_empty,
                              knowledge_has_embeddings)
from lib.embeddings import embedding_dim, provider_name
from lib import queries
from seed_data import seed as run_seed

st.set_page_config(page_title="Field Advisor — Grower Assistant",
                   page_icon="🌾", layout="wide")

SEVERITY_COLOR = {"Low": "#059669", "Medium": "#d97706",
                  "High": "#dc2626", "Critical": "#991b1b"}
STATUS_COLOR = {"open": "#dc2626", "in_progress": "#d97706", "resolved": "#059669"}
SOURCE_ICON = {"vector": "🧠 semantic", "keyword": "🔤 keyword", "hybrid": "🧠🔤 hybrid"}


@st.cache_resource
def _db():
    return get_db()


def badge(text: str, color: str) -> str:
    return (f"<span style='background:{color}1a;color:{color};padding:2px 8px;"
            f"border-radius:10px;font-size:0.8em;font-weight:600'>{text}</span>")


def chips(values: list[str], color: str = "#6b7280") -> str:
    return " ".join(badge(v, color) for v in values if v)


# ── Sidebar: connection, seeding, navigation ────────────────────────────────

def render_sidebar() -> str:
    st.sidebar.markdown("## 🌾 Field Advisor")
    st.sidebar.caption("Grower assistant · powered by MongoDB Atlas")

    try:
        db = _db()
        db.command("ping")
        st.sidebar.success(f"Atlas connected · `{db_name()}`")
    except Exception as e:
        st.sidebar.error(f"Not connected: {e}")
        st.stop()

    st.sidebar.caption(f"Embeddings: `{provider_name()}` · dim `{embedding_dim()}`")

    if is_empty():
        st.sidebar.warning("No data yet. Seed to begin.")
        if st.sidebar.button("🌱 Seed demo data", use_container_width=True):
            with st.spinner("Seeding synthetic growers, fields, cases, and "
                            "knowledge base…"):
                run_seed(24)
            st.toast("Seeded. Now run scripts/create_indexes.py for search.")
            st.rerun()
        st.stop()

    if not knowledge_has_embeddings():
        st.sidebar.info("Knowledge base has no embeddings yet — re-run "
                        "`python3 seed_data.py`.")

    st.sidebar.markdown("---")
    page = st.sidebar.radio(
        "Workflow",
        ["🔎 Advisory Search", "👤 Operational Context", "💡 Why Atlas"])
    st.sidebar.markdown("---")
    st.sidebar.caption("Tip: run `scripts/create_indexes.py` once so the "
                       "vector (and optional keyword) indexes exist in Atlas.")
    return page


# ── Workflow 1: Advisory Search (hybrid retrieval) ──────────────────────────

def _filter_controls() -> dict:
    st.markdown("##### Structured filters (operational data)")
    c1, c2, c3, c4, c5 = st.columns(5)
    return {
        "crop": c1.selectbox("Crop", [""] + CROPS),
        "region": c2.selectbox("Region", [""] + REGIONS),
        "season": c3.selectbox("Season", [""] + SEASONS),
        "product_line": c4.selectbox("Product line", [""] + PRODUCT_LINES),
        "severity": c5.selectbox("Severity", [""] + SEVERITIES),
    }


def render_advisory() -> None:
    db = _db()
    st.markdown("## 🔎 Advisory Search")
    st.caption("Ask a natural-language grower question, optionally narrow with "
               "structured filters. Atlas runs semantic vector search over the "
               "knowledge base **and** filters operational cases — in one flow.")

    query = st.text_input(
        "Grower question / crop symptom / support request",
        placeholder="e.g. lower leaves on my corn are turning yellow after rain")
    filters = _filter_controls()
    go = st.button("Search Atlas", type="primary")

    if not (go and query.strip()):
        st.info("Enter a question and press **Search Atlas** to run the "
                "hybrid retrieval flow.")
        return

    with st.spinner("Running vector search + structured filter in Atlas…"):
        result = queries.hybrid_advisory(db, query, filters, limit=6)
        cases = queries.matching_cases(db, filters, limit=15)

    left, right = st.columns([3, 2], gap="large")
    with left:
        _render_knowledge_results(result["articles"])
    with right:
        _render_matching_cases(cases)

    _render_how_it_works(result["debug"], len(cases))


def _render_knowledge_results(articles: list[dict]) -> None:
    st.markdown("#### 🧠 Relevant guidance (Atlas Vector Search)")
    if not articles:
        st.warning("No knowledge articles matched. If you just seeded, make "
                   "sure `scripts/create_indexes.py` has finished building the "
                   "vector index (allow 1-2 minutes).")
        return
    for a in articles:
        with st.container(border=True):
            st.markdown(f"**{a.get('title', '?')}**")
            st.markdown(
                chips([a.get("crop"), a.get("region"), a.get("season"),
                       a.get("product_line")])
                + " " + badge(a.get("severity", "-"),
                              SEVERITY_COLOR.get(a.get("severity"), "#6b7280")),
                unsafe_allow_html=True)
            st.write(a.get("summary", ""))
            with st.expander("Full guidance & match detail"):
                st.write(a.get("body", ""))
                st.caption(SOURCE_ICON.get(a.get("source"), a.get("source", "")))
                if a.get("fused_score") is not None:
                    st.caption(f"Fused relevance score: {a['fused_score']}")


def _render_matching_cases(cases: list[dict]) -> None:
    st.markdown("#### 📁 Matching open cases (operational data)")
    st.caption("Same filters applied to the system-of-record `support_cases`.")
    if not cases:
        st.caption("No operational cases match these filters.")
        return
    for c in cases[:8]:
        with st.container(border=True):
            st.markdown(
                f"**{c.get('case_id')}** · "
                + badge(c.get("severity", "-"),
                        SEVERITY_COLOR.get(c.get("severity"), "#6b7280"))
                + " " + badge(c.get("status", "-"),
                              STATUS_COLOR.get(c.get("status"), "#6b7280")),
                unsafe_allow_html=True)
            st.caption(f"{c.get('crop')} · {c.get('region')} · {c.get('season')}")
            st.write(c.get("summary", ""))


def _render_how_it_works(debug: dict, case_count: int) -> None:
    with st.expander("💡 How this works (one Atlas backend, two capabilities)"):
        st.markdown(
            "- **Semantic retrieval** ran against the Atlas Vector Search index "
            f"`{debug['vector_index']}` → **{debug['vector_hits']}** hits.\n"
            "- **Keyword retrieval** (optional Atlas Search index "
            f"`{debug['keyword_index']}`) → **{debug['keyword_hits']}** hits "
            "(0 if the keyword index isn't built — the app still works).\n"
            f"- Results were fused with **{debug['fusion']}**.\n"
            f"- The **same structured filters** narrowed **{case_count}** "
            "operational `support_cases` documents.\n\n"
            "Operational records and vectorized knowledge live in **one Atlas "
            "database** — this screen combines both in a single experience.")
        if debug["filters_applied"]:
            st.json(debug["filters_applied"])


# ── Workflow 2: Operational Context (read + write-back) ─────────────────────

def render_operational() -> None:
    db = _db()
    st.markdown("## 👤 Operational Context")
    st.caption("Open a grower record to see fields, open issues, product "
               "history, and recent interactions — then write a note, "
               "recommendation, or follow-up status back to Atlas.")

    growers = queries.list_growers(db)
    labels = {f"{g['grower_id']} — {g['name']} · {g['farm_name']} "
              f"({g['region']})": g["grower_id"] for g in growers}
    if not labels:
        st.info("No growers. Seed data first.")
        return
    chosen = st.selectbox("Select a grower", list(labels.keys()))
    ov = queries.grower_overview(db, labels[chosen])
    g = ov["grower"]
    if not g:
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total acres", f"{g.get('total_acres', 0):,}")
    c2.metric("Fields", len(ov["fields"]))
    c3.metric("Open issues", len(ov["open_cases"]))
    c4.metric("Tier", g.get("tier", "-").replace("_", " ").title())
    st.markdown("**Primary crops:** "
                + chips(g.get("primary_crops", []), "#2563eb"),
                unsafe_allow_html=True)

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("#### 📁 Open issues")
        if ov["open_cases"]:
            for c in ov["open_cases"]:
                st.markdown(
                    badge(c.get("severity", "-"),
                          SEVERITY_COLOR.get(c.get("severity"), "#6b7280"))
                    + " " + badge(c.get("status", "-"),
                                  STATUS_COLOR.get(c.get("status"), "#6b7280"))
                    + f" **{c.get('case_id')}** — {c.get('crop')}",
                    unsafe_allow_html=True)
                st.caption(c.get("summary", ""))
                st.caption("👉 Recommended next action: "
                           + c.get("recommended_action", "—"))
        else:
            st.caption("No open issues for this grower.")

        st.markdown("#### 🧴 Product history")
        st.markdown(chips(ov["product_lines"], "#7c3aed") or "—",
                    unsafe_allow_html=True)
    with right:
        st.markdown("#### 🕑 Recent interactions")
        for it in ov["interactions"]:
            st.markdown(f"- `{it['created_at'].strftime('%Y-%m-%d %H:%M')}` "
                        f"· **{it.get('type')}** · {it.get('author')}")
            st.caption(it.get("text", ""))
        if not ov["interactions"]:
            st.caption("No interactions logged yet.")

    _render_writeback(ov)


def _render_writeback(ov: dict) -> None:
    db = _db()
    st.markdown("---")
    st.markdown("#### ✍️ Write back to Atlas")
    if not ov["cases"]:
        st.caption("This grower has no cases to update.")
        return
    case_labels = {f"{c['case_id']} — {c.get('crop')} ({c.get('status')})":
                   c["case_id"] for c in ov["cases"]}
    with st.form("writeback", clear_on_submit=True):
        cols = st.columns([2, 2, 3])
        case_key = cols[0].selectbox("Case", list(case_labels.keys()))
        kind = cols[1].selectbox("Type", ["note", "recommendation", "follow_up"])
        status = cols[2].selectbox(
            "Update status (optional)", ["", "open", "in_progress", "resolved"])
        text = st.text_area("Note / recommendation / follow-up",
                            placeholder="Confirmed leaf rust on the flag leaf; "
                                        "recommend a fungicide pass this week.")
        submitted = st.form_submit_button("Save to Atlas", type="primary")
    if submitted and text.strip():
        queries.add_interaction(
            db, case_labels[case_key], ov["grower"]["grower_id"],
            kind=kind, text=text.strip(),
            new_status=status or None)
        st.success("Written to Atlas: appended to the case and "
                   "`interaction_history`.")
        st.rerun()


# ── Workflow 3: Why Atlas ───────────────────────────────────────────────────

def render_why_atlas() -> None:
    db = _db()
    st.markdown("## 💡 Why Atlas")
    st.caption("One managed backend for both the operational app and semantic "
               "search — not two systems stitched together.")

    op_docs = sum(db[c].count_documents({}) for c in
                  ["growers", "fields", "products", "support_cases",
                   "interaction_history"])
    vec_docs = db.knowledge_articles.count_documents(
        {"embedding": {"$exists": True}})

    c1, c2, c3 = st.columns(3)
    c1.metric("Operational documents", f"{op_docs:,}")
    c2.metric("Vectorized knowledge docs", f"{vec_docs:,}")
    c3.metric("Backends to run", "1")

    st.markdown("""
| In this demo | Lives in Atlas as | Powers |
|---|---|---|
| Growers, fields, cases, interactions | Document collections | The operational app (read + write-back) |
| Agronomy knowledge base | Documents **+ vector embeddings** | Semantic advisory search |
| Structured filters | Indexed fields + vector filters | Narrowing both sides consistently |
""")
    st.info("The **Advisory Search** screen queries both at once: vector search "
            "for guidance, structured filters for operational cases — combined "
            "in a single grower-facing experience.")
    st.markdown("**Pluggable embeddings:** this demo defaults to a "
                "zero-dependency local embedder so it runs anywhere. Set "
                "`EMBEDDING_PROVIDER=voyage` (and `EMBEDDING_DIM=1024`) in `.env` "
                "to swap in production-grade embeddings — no other code changes.")


# ── Main router ─────────────────────────────────────────────────────────────

def main() -> None:
    page = render_sidebar()
    if page.startswith("🔎"):
        render_advisory()
    elif page.startswith("👤"):
        render_operational()
    else:
        render_why_atlas()

    st.markdown("---")
    st.caption("Illustrative demo — MongoDB Atlas is the system of record for "
               "both operational data and vector search. Synthetic data only.")


main()
