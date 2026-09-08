"""Shared Streamlit chrome so every section looks and behaves the same.

Holds the cached connection, the connection/seed guards, presenter mode, the
confirmed `Reset demo data` control, and the large-type table/JSON helpers used
at presentation zoom.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from bson import json_util
from pymongo.errors import PyMongoError

from lib.mongo_client import DB_NAME, MissingUriError, get_db, is_empty
from lib.seed import reset_transaction_demo, seed

TITLE = "MongoDB Foundations: Live Walkthrough"
SUBTITLE = "Concepts are general MongoDB; Atlas is the demo environment."

PRESENTER_CSS = """
<style>
  section.main div[data-testid="stDataFrame"] { font-size: 1.15rem; }
  section.main pre, section.main code { font-size: 1.05rem; }
  section.main h2 { margin-top: 0.2rem; }
</style>
"""


@st.cache_resource
def _database():
    """Cached database handle. Only the connection is cached, never data."""
    return get_db()


def db():
    return _database()


def page_setup(title: str, icon: str = "🍃") -> None:
    st.set_page_config(page_title="{} · {}".format(title, TITLE),
                       page_icon=icon, layout="wide")
    st.markdown(PRESENTER_CSS, unsafe_allow_html=True)


def presenter_mode() -> bool:
    """Sidebar toggle: minimal prose, large output, fewer controls."""
    return st.sidebar.toggle(
        "Presenter mode", value=True, key="presenter_mode",
        help="On: minimal prose and large output. Off: full explanations.")


def prose(markdown: str) -> None:
    """Explanatory text that is hidden in presenter mode."""
    if not st.session_state.get("presenter_mode", True):
        st.markdown(markdown)


def page_header(number: str, title: str, one_liner: str) -> None:
    st.markdown("## {} {}".format(number, title))
    st.caption(one_liner)


def cue(text: str) -> None:
    """A presenter cue — always visible, deliberately short."""
    st.info("🎤 **Presenter cue** · {}".format(text))


def takeaway(text: str) -> None:
    st.success("**Takeaway** · {}".format(text))


def synthetic_note() -> None:
    st.caption("🧪 Synthetic demo data — invented for this session. No real "
               "customer, account, or personal data.")


def table(rows, empty_message: str = "No rows returned.") -> None:
    """Large, readable table output."""
    if not rows:
        st.warning(empty_message)
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def mql(obj, language: str = "javascript") -> None:
    """Show a filter, pipeline, or document as readable extended JSON."""
    st.code(json_util.dumps(obj, indent=2), language=language)


def connection_guard() -> None:
    """Stop the page with actionable guidance when the demo cannot connect."""
    try:
        handle = db()
        handle.command("ping")
        st.sidebar.success("Connected · `{}`".format(DB_NAME))
    except MissingUriError:
        st.sidebar.error("No MONGODB_URI")
        st.error("**Missing configuration.** Copy `.env.example` to `.env`, set "
                 "`MONGODB_URI`, then reload this page.")
        st.stop()
    except PyMongoError as exc:
        st.sidebar.error("Deployment unreachable")
        st.error("**Cannot reach the deployment.** Check the connection string, "
                 "the database user, and that this machine's IP is on the "
                 "deployment's access list.")
        with st.expander("Connection error detail"):
            st.write(str(exc))
        st.stop()


def seed_guard() -> None:
    """Stop the page when the demo namespace is empty, and offer the fix."""
    try:
        empty = is_empty()
    except (MissingUriError, PyMongoError) as exc:
        st.error("**Cannot read the demo database.** {}".format(exc))
        st.stop()
        return
    if empty:
        st.warning("**No demo data yet.** This section needs the seed.")
        st.markdown("Seed from the sidebar, or from the command line:")
        st.code("python3 seed_data.py", language="bash")
        st.stop()


def sidebar_reset() -> None:
    """The confirmed `Reset demo data` control, present on every page."""
    with st.sidebar:
        st.markdown("---")
        st.markdown("### Demo data")
        st.caption("Scope: database `{}` only.".format(DB_NAME))

        if st.button("↺ Reset demo data", use_container_width=True):
            st.session_state["reset_pending"] = True

        if st.session_state.get("reset_pending"):
            st.warning("Drops and re-seeds the three collections in `{}`. No "
                       "other database is touched.".format(DB_NAME))
            confirm, cancel = st.columns(2)
            if confirm.button("Confirm", type="primary",
                              use_container_width=True):
                st.session_state["reset_pending"] = False
                try:
                    result = seed()
                    st.success("Reset complete · {}".format(
                        " · ".join("{}={}".format(k, v)
                                   for k, v in result.items())))
                except (MissingUriError, PyMongoError) as exc:
                    st.error("Reset failed: {}".format(exc))
            if cancel.button("Cancel", use_container_width=True):
                st.session_state["reset_pending"] = False
                st.rerun()

        if st.button("↺ Reset transaction demo only", use_container_width=True,
                     help="Restores the two demo balances and removes the "
                          "ledger entries this demo wrote."):
            try:
                result = reset_transaction_demo()
                st.success("Balances restored · {} demo entries removed"
                           .format(result["demo_transfers_removed"]))
            except (MissingUriError, PyMongoError) as exc:
                st.error("Reset failed: {}".format(exc))
