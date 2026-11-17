"""⑤ Architecture considerations — what is confirmed, what is open."""

import streamlit as st

from lib.config import execution_mode, get_client
from lib.ui import connection_guard, demo_scope_note, synthetic_note

st.set_page_config(page_title="Architecture considerations · SMB demo",
                   page_icon="🧭", layout="wide")
connection_guard()

st.markdown("# ⑤ Architecture considerations")
st.caption("What the current workload shares, what the SMB extension could "
           "look like, and what remains deliberately undecided.")
synthetic_note()
demo_scope_note()

st.markdown("### Where this data lives today (✅ confirmed)")
st.markdown(
    "- The **existing branded-calling application** stores customer, logo, "
    "and telephone-number information. A telephone-number asset can carry "
    "partner-interaction data (`partnerData`).\n"
    "- **Other trusted-calling services share that workload** — this demo's "
    "`accounts` and `numberAssets` shapes describe that shared data, not a "
    "new silo.\n"
    "- A separate **robocall-mitigation workload** (~1.8 billion records) "
    "runs **separately**. It is intentionally absent from this demo's data "
    "model — nothing on these pages represents that workload.")

st.markdown("### The open SMB decision (⏳ not settled)")
st.warning("**Whether SMB traffic uses a separate cluster/silo is an open "
           "architecture decision.** This demo shows *logical* isolation by "
           "writing to its own demo database — a safety property of the "
           "walkthrough, **not** a resolution of the production deployment "
           "question. No final topology is recommended here.")

st.markdown("### Atomicity strategy on this deployment")
st.info(f"This walkthrough detects the connected deployment at runtime and "
        f"chooses the write path: **{execution_mode(get_client())}**.\n\n"
        "- **Transactions (replica set / sharded):** counter reservation, "
        "asset inserts, and audit events commit or roll back together — "
        "truly atomic.\n"
        "- **Fallback (standalone):** reservation-first with compensation — "
        "the counter is reserved atomically, then assets are inserted; any "
        "failed insert refunds capacity exactly once. This path is a "
        "documented, deliberate **non-atomic** sequence across collections, "
        "with the per-account counter as the reconciliation anchor.")

st.markdown("### Questions this walkthrough is designed to provoke")
for q in [
    "If SMB becomes a separate silo, which services still need a joined view "
    "of number assets with the shared workload?",
    "Should the counter document live beside the assets it governs, or can "
    "cap enforcement tolerate eventual reconciliation?",
    "What verification/vetting evidence must accompany reactivation and "
    "transfer, given both count as additions?",
    "Which audit events are retention-relevant for compliance, and for how "
    "long?",
]:
    st.markdown(f"- {q}")

st.caption("This demo does not deploy, publish, or provision anything. It "
           "performs targeted writes only inside the demo database, only "
           "when you press a button.")
