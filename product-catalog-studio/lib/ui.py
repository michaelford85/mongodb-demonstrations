"""Shared Streamlit UI helpers for Product Catalog Studio.

Keeps every page visually consistent: a cached DB handle, colored badges, the
connection and seed guards, and the synthetic-data disclosure. Pages import these
so the shared chrome lives in one place and each page file stays focused on its
single topic.

Presenter talk tracks deliberately live in the README, not in the app — the
screen shown to an audience carries only the demo content.
"""

from __future__ import annotations

import streamlit as st

from lib.atlas_client import (BRAND, TYPE_LABELS, db_name, get_db, is_empty)

STATUS_COLOR = {"active": "#059669", "limited": "#d97706",
                "preorder": "#2563eb", "discontinued": "#6b7280"}
TYPE_COLOR = {"equipment": "#2563eb", "consumable": "#7c3aed",
              "service_plan": "#0f766e"}
MODE_COLOR = {"keyword": "#d97706", "semantic": "#7c3aed", "hybrid": "#059669"}


@st.cache_resource
def db():
    """Cached demo database handle, shared across all pages."""
    return get_db()


def badge(text: str, color: str = "#6b7280") -> str:
    return (f"<span style='background:{color}1a;color:{color};padding:2px 8px;"
            f"border-radius:10px;font-size:0.8em;font-weight:600'>{text}</span>")


def chips(values: list[str], color: str = "#6b7280") -> str:
    return " ".join(badge(v, color) for v in values if v)


def status_badge(status: str) -> str:
    return badge(status.title(), STATUS_COLOR.get(status, "#6b7280"))


def type_badge(product_type: str) -> str:
    return badge(TYPE_LABELS.get(product_type, product_type),
                 TYPE_COLOR.get(product_type, "#6b7280"))


def synthetic_note() -> None:
    """The standard, non-negotiable 'this is synthetic demo data' caption."""
    st.caption(f"🧪 Synthetic demo data — {BRAND} is an invented brand and every "
               "product, SKU, price, and specification here was made up for this "
               "demonstration. No real company or customer data.")


def connection_guard() -> None:
    """Stop the page early with actionable guidance if Atlas is unreachable."""
    try:
        handle = db()
        handle.command("ping")
        st.sidebar.success(f"Atlas connected · `{db_name()}`")
    except Exception as e:  # noqa: BLE001 — surface the real cause to presenter
        st.sidebar.error(f"Not connected to Atlas: {e}")
        st.error("**Missing configuration.** Copy `.env.example` to `.env`, set "
                 "`MONGODB_URI` to an existing Atlas cluster, then reload this "
                 "page.")
        st.stop()


def seed_guard() -> None:
    """Stop the page with guidance when the demo has not been seeded yet."""
    if is_empty():
        st.warning("No catalog data yet. This page needs the seed to run.")
        st.markdown("Run the seed once from the project root:")
        st.code("python3 seed_data.py", language="bash")
        st.info("Or open the **Demo Readiness** page and use **Seed demo data**.")
        st.stop()


def page_header(icon: str, title: str, tagline: str) -> None:
    """Consistent page title + one-line business framing."""
    st.markdown(f"## {icon} {title}")
    st.caption(tagline)


def story_arc(problem: str, interaction: str, mechanism: str,
              tradeoff: str) -> None:
    """The four-beat story arc shown near the top of every demo route."""
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"**① Business problem**\n\n{problem}")
    c2.markdown(f"**② Interaction**\n\n{interaction}")
    c3.markdown(f"**③ MongoDB mechanism**\n\n{mechanism}")
    c4.markdown(f"**④ Trade-off**\n\n{tradeoff}")
    st.markdown("---")


def query_panel(label: str, payload, *, expanded: bool = False) -> None:
    """Show the exact query or pipeline that produced what is on screen."""
    with st.expander(f"🔎 {label}", expanded=expanded):
        st.json(payload, expanded=True)


def product_card(doc: dict, *, footer: str | None = None) -> None:
    """Compact, business-readable product card used by list and result views."""
    price = doc.get("price") or {}
    st.markdown(f"**{doc.get('name', '—')}** · `{doc.get('sku', '—')}`  \n"
                + type_badge(doc.get("product_type", ""))
                + " " + status_badge(doc.get("status", ""))
                + " " + badge(doc.get("category", "—"), "#334155"),
                unsafe_allow_html=True)
    st.caption(doc.get("summary", "—"))
    st.markdown(f"{price.get('amount', 0):,.2f} {price.get('currency', '')} "
                f"{price.get('unit', '')}".strip())
    if doc.get("tags"):
        st.markdown(chips(doc["tags"], "#0f766e"), unsafe_allow_html=True)
    if footer:
        st.caption(footer)
