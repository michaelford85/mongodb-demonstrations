"""Streamlit UI helpers: connection guard, badges, and the standard
synthetic-data disclosure. No database writes happen here — every write is
behind an explicit button on a page."""

from __future__ import annotations

import streamlit as st

from lib.config import (DEFAULT_DEMO_DB, NUMBER_ASSETS_COLLECTION, db_name,
                        get_client, get_db)


@st.cache_resource
def db():
    """Cached demo-database handle, shared across all pages."""
    return get_db()


def badge(text: str, color: str = "#6b7280") -> str:
    return (f"<span style='background:{color}1a;color:{color};padding:2px 8px;"
            f"border-radius:10px;font-size:0.8em;font-weight:600'>{text}</span>")


def ok_badge(text: str) -> str:
    return badge(text, "#059669")


def err_badge(text: str) -> str:
    return badge(text, "#dc2626")


def synthetic_note() -> None:
    st.caption("🧪 Synthetic demo data — every account, brand, and telephone "
               "number here was invented for this demonstration (numbers use "
               "the reserved fictional range +1-555-01xx). No real customer "
               "or personal data.")


def connection_guard() -> None:
    """Stop the page early with actionable guidance if the cluster is
    unreachable. Shows the demo database and collection names — never the
    connection string."""
    try:
        get_client().admin.command("ping")
    except Exception as exc:
        st.error("**No database connection.** This demo reads its connection "
                 "string from the `.env` file in this folder "
                 "(`MONGODB_URI`, never displayed). Populate it from your "
                 "approved local secret source and reload.")
        st.caption(f"Underlying error type (no credentials shown): "
                   f"{type(exc).__name__}")
        st.stop()
    if get_db_name_mismatch():
        st.warning("The connection string points at a default database, but "
                   "this demo only reads and writes the dedicated demo "
                   "database shown below — the connection string's default "
                   "database is never used.")


def get_db_name_mismatch() -> bool:
    # Always true by design: the demo database is chosen by DEMO_DATABASE,
    # never inferred from the connection string.
    return True


def demo_scope_note() -> None:
    st.caption(f"🗄️ Demo database: `{db_name()}` (override with "
               f"`DEMO_DATABASE`; default `{DEFAULT_DEMO_DB}`). Collections: "
               f"`accounts`, `{NUMBER_ASSETS_COLLECTION}`, "
               f"`provisioningCounters`, `provisioningAudit`. All records are "
               f"labelled synthetic demo data.")


def writes_blocked_banner() -> None:
    """Shown when safe isolation cannot be verified."""
    st.error("Writes are disabled: the demo database could not be verified "
             "as isolated. No seed or ingestion actions are available.")
