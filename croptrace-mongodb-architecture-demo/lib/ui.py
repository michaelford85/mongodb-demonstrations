"""Shared Streamlit UI helpers for the CropTrace demo.

Keeps every page visually consistent: a cached DB handle, colored status
badges, a standard connection/seed guard, a presenter-notes accordion, and a
per-page reset action. Pages import these so the story-telling chrome stays in
one place and the page files stay focused on their single topic.
"""

from __future__ import annotations

import streamlit as st

from lib.atlas_client import db_name, get_db, is_empty

RISK_COLOR = {"low": "#059669", "moderate": "#d97706",
              "elevated": "#ea580c", "high": "#dc2626"}
STATUS_COLOR = {"planned": "#2563eb", "applied": "#059669", "cancelled": "#6b7280"}
CATEGORY_COLOR = {"Fungicide": "#7c3aed", "Insecticide": "#dc2626",
                  "Herbicide": "#d97706", "Biocontrol": "#059669"}


@st.cache_resource
def db():
    """Cached demo database handle, shared across all pages."""
    return get_db()


def badge(text: str, color: str = "#6b7280") -> str:
    return (f"<span style='background:{color}1a;color:{color};padding:2px 8px;"
            f"border-radius:10px;font-size:0.8em;font-weight:600'>{text}</span>")


def chips(values: list[str], color: str = "#6b7280") -> str:
    return " ".join(badge(v, color) for v in values if v)


def synthetic_note() -> None:
    """The standard, non-negotiable 'this is synthetic demo data' caption."""
    st.caption("🧪 Synthetic demo data — invented for this demonstration. "
               "No real grower, farm, product, or customer data.")


def connection_guard() -> None:
    """Stop the page early with actionable guidance if Atlas is unreachable."""
    try:
        handle = db()
        handle.command("ping")
        st.sidebar.success(f"Atlas connected · `{db_name()}`")
    except Exception as e:  # noqa: BLE001 — surface the real cause to presenter
        st.sidebar.error(f"Not connected to Atlas: {e}")
        st.error("**Missing configuration.** Copy `.env.example` to `.env`, set "
                 "`MONGODB_URI` to the cluster from `atlas-cluster-provisioning`, "
                 "then reload this page.")
        st.stop()


def seed_guard() -> None:
    """Stop the page with guidance when the demo has not been seeded yet."""
    if is_empty():
        st.warning("No demo data yet. This route needs the seed to run.")
        st.markdown("Run the seed once from the project root:")
        st.code("python3 seed_data.py", language="bash")
        st.info("Or open the **Demo Readiness** page and use **Seed demo data**.")
        st.stop()


def presenter_notes(*, talk_track: str, click_path: list[str],
                    takeaway: str, caveat: str) -> None:
    """Render the standard presenter-notes accordion for a route.

    Every route exposes the same shape: a 60-90 second talk track, the exact
    click path, the one-line technical takeaway, and the honest caveat.
    """
    with st.expander("🎤 Presenter notes (60–90 second talk track)"):
        st.markdown("**Talk track**")
        st.write(talk_track)
        st.markdown("**Exact click path**")
        for i, step in enumerate(click_path, 1):
            st.markdown(f"{i}. {step}")
        st.markdown("**Technical takeaway**")
        st.success(takeaway)
        st.markdown("**Caveat / when PostgreSQL may be the better fit**")
        st.warning(caveat)


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
