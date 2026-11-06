"""SMB Number Provisioning — a document-database walkthrough.

A presenter-ready Streamlit demo of an SMB telephone-number provisioning
flow: three entry routes, one shared validation + cap-enforcement service,
atomic per-account capacity, and an audit trail.

Every account, brand, and telephone number in this demo is synthetic
(numbers come from the reserved fictional range +1555555xxxx (fictional 555/555 exchange)). All reads and
writes are confined to the dedicated demo database named in the page header.

    streamlit run app.py
"""

import streamlit as st

from lib.ui import connection_guard, demo_scope_note, synthetic_note

st.set_page_config(page_title="SMB Number Provisioning · document DB demo",
                   page_icon="📞", layout="wide")

connection_guard()

st.markdown("# 📞 SMB Number Provisioning Walkthrough")
st.caption("How an SMB offering could add telephone-number provisioning on a "
           "document database — three entry routes, one shared enforcement "
           "path, per-account caps, and an audit trail.")

synthetic_note()
demo_scope_note()

st.info("**Scope in one line.** This demo models the *existing branded-calling* "
        "workload's account and number-asset data — the same workload shared "
        "by other trusted-calling services — plus a proposed SMB extension. "
        "A separate high-volume robocall-mitigation workload (~1.8 billion "
        "records) runs elsewhere and is **out of scope** here.")

st.markdown("### The flow")
st.markdown(
    "1. **The account supplies its own numbers** — the service verifies the "
    "customer's right to use each number (shown here as a conceptual "
    "vetting step; this demo does not perform real verification or vetting).\n"
    "2. Numbers enter through one of **three routes**: a portal-style UI, a "
    "batch-file upload, or the direct API. All three call the *same* "
    "validation and ingestion service, so cap enforcement cannot diverge.\n"
    "3. A **per-account cap check** reserves capacity with one atomic "
    "conditional update on a shared counter.\n"
    "4. The result is either an **accepted number asset** or a rejection "
    "(`422 SERVICE_PACKAGE_CAP_EXCEEDED`) with an audit event — over-cap "
    "requests are rejected, not queued.")

c1, c2, c3 = st.columns(3)
for col, path, title, desc in [
    (c1, "pages/1_Ingest_Numbers.py", "① Ingest numbers",
     "Portal entry, CSV batch upload, and direct-API simulation — one shared "
     "service, plus reactivation/transfer examples."),
    (c2, "pages/2_Concurrency_Race.py", "② Concurrency race",
     "The 99-of-100 race: two concurrent one-number requests, exactly one "
     "succeeds, the other gets 422."),
    (c3, "pages/3_Schema_and_Indexes.py", "③ Schema & indexes",
     "Readable JSON examples for accounts and numberAssets, the unique "
     "asset index, and the recommended counter schema."),
]:
    with col:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(desc)
            st.page_link(path, label="Open →")

c4, c5 = st.columns(2)
for col, path, title, desc in [
    (c4, "pages/4_Results_and_Audit.py", "④ Results & audit",
     "Accepted/rejected outcomes, per-row batch results, capacity usage, "
     "PROVISIONING_REJECTED examples, and safe capacity controls."),
    (c5, "pages/5_Architecture_Considerations.py", "⑤ Architecture considerations",
     "What is confirmed vs. proposed — including the unresolved SMB "
     "isolation decision and the out-of-scope robocall workload."),
]:
    with col:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(desc)
            st.page_link(path, label="Open →")

st.markdown("---")
st.markdown("### Open architecture decision (not settled)")
st.warning("Whether SMB traffic uses a **separate cluster/silo is an open "
           "decision**. This walkthrough demonstrates *logical* isolation in "
           "its own demo database purely so the flows are safe to run — that "
           "does **not** resolve how production would deploy.")
st.caption("Writes never happen on page load. Seeding and every ingestion "
           "scenario require an explicit button press, and writes are "
           "idempotent and confined to the demo database.")
