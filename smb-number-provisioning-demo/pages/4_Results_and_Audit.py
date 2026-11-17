"""④ Results & audit — outcomes, capacity usage, audit trail, capacity controls."""

from datetime import datetime, timezone

import streamlit as st

from lib.cap_service import (CAP_TYPE, DEFAULT_CAP, lower_cap, remove_number,
                             states_counting_toward_cap)
from lib.config import (AUDIT_COLLECTION, COUNTERS_COLLECTION,
                        NUMBER_ASSETS_COLLECTION, RACE_ACCOUNT_ID)
from lib.ui import connection_guard, demo_scope_note, synthetic_note

st.set_page_config(page_title="Results & audit · SMB provisioning demo",
                   page_icon="📋", layout="wide")
connection_guard()

st.markdown("# ④ Results & audit")
st.caption("Accepted and rejected outcomes, per-row batch results, live "
           "capacity usage, and the audit trail — synthetic demo records only.")
synthetic_note()
demo_scope_note()

db = None  # pages use the cached handle via get_db()


def get_db():
    from lib.ui import db as cached_db
    return cached_db()


st.markdown("### Capacity usage (demo counters)")
counters = list(get_db()[COUNTERS_COLLECTION].find(
    {}, {"_id": 0}).limit(20).sort("accountId", 1))
if counters:
    st.dataframe(counters, use_container_width=True)
    st.caption("All values are synthetic demo data. The counter document is "
               "a demo/design recommendation, not a confirmed collection.")
else:
    st.info("No counters yet — run a scenario on the Ingest page or press "
            "**Reset race account** on the Concurrency page.")

st.markdown("### Recent audit events")
events = list(get_db()[AUDIT_COLLECTION].find({}, {"_id": 0})
              .sort("at", -1).limit(25))
if events:
    for e in events:
        icon = "✅" if e.get("event") == "PROVISIONING_ACCEPTED" else "🚫"
        st.markdown(
            f"{icon} `{e.get('event')}` · `{e.get('accountId')}` · "
            f"requested {e.get('requestedCount')} · `{e.get('resultCode')}` · "
            f"channel `{e.get('channel')}` · key `{e.get('idempotencyKey')}`")
    st.caption(f"`PROVISIONING_REJECTED` examples above show the "
               f"`422 SERVICE_PACKAGE_CAP_EXCEEDED` outcome with no number "
               f"saved. Bounded read: last {len(events)} events.")
else:
    st.info("No audit events yet.")

st.markdown("### Capacity controls (deliberate actions only)")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Lower the cap below current usage.** Existing numbers are "
                "kept; new additions are blocked until usage falls below "
                "the cap.")
    acc = st.text_input("Account", RACE_ACCOUNT_ID, key="lc_account")
    new_cap = st.number_input("New cap", min_value=0, max_value=10_000,
                              value=50, key="lc_cap")
    if st.button("Lower cap", key="lc_btn"):
        doc = lower_cap(get_db(), acc.strip(), int(new_cap))
        if doc:
            st.success(f"Cap for `{acc}` is now {doc['cap']} with "
                       f"activeCount={doc['activeCount']} — "
                       f"{'additions blocked until usage is below the cap'
                         if doc['activeCount'] >= doc['cap'] else 'accepting additions'}.")
        else:
            st.error("No counter for that account yet.")
with c2:
    st.markdown("**Remove an eligible number.** Capacity is freed exactly "
                "once. States that count toward the cap: "
                f"`{sorted(states_counting_toward_cap())}`.")
    r_acc = st.text_input("Account ", "ACC-SMB-0001", key="rm_account")
    r_tn = st.text_input("Number", "+15555550100", key="rm_tn")
    if st.button("Remove number", key="rm_btn"):
        ok, msg = remove_number(get_db(), r_acc.strip(), r_tn.strip())
        (st.success if ok else st.warning)(msg)

st.markdown("### Start from scratch (safe reset)")
st.caption("Reset = targeted cleanup of every record **created by this demo** "
           "— including seed data — in the demo database only. It never "
           "drops a database or collection and never touches anything "
           "outside the demo collections.")
confirm = st.checkbox("I understand this deletes all of this demo's synthetic "
                      "records (seed data, ingested assets, counters, audit "
                      "events) from the demo database", key="confirm_reset")
if st.button("Reset walkthrough — start from scratch", disabled=not confirm,
             key="reset_btn"):
    from lib.sample_data import reset_demo_records
    removed = reset_demo_records(get_db())
    for coll, n in removed.items():
        st.caption(f"`{coll}`: removed {n} synthetic demo record(s)")
    st.success("Back to a blank slate. Nothing outside the demo collections "
               "was touched. Seed again from the Ingest page to start over.")
    st.session_state["seed_info"] = None
