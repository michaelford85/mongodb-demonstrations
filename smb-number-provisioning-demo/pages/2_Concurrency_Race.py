"""② Concurrency race — the 99-of-100 demonstration.

Two concurrent one-number requests hit an account at 99/100. The atomic
conditional counter update means exactly one succeeds and the other is
rejected with 422 SERVICE_PACKAGE_CAP_EXCEEDED. The setup button makes the
result repeatable; no dependence on UI timing.
"""

from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from lib.cap_service import (CAP_EXCEEDED, CAP_TYPE, DEFAULT_CAP, BatchResult,
                             process_ingest, set_counter_for_demo)
from lib.config import RACE_ACCOUNT_ID
from lib.sample_data import FICTIONAL_TNS, seed_demo
from lib.ui import (connection_guard, demo_scope_note, err_badge, ok_badge,
                    synthetic_note)

st.set_page_config(page_title="Concurrency race · SMB provisioning demo",
                   page_icon="🏁", layout="wide")
connection_guard()

st.markdown("# ② The 99-of-100 race")
st.caption("The cap is per account record, keyed by unique `accountId`. With "
           "the account at 99 of 100 and two concurrent one-number requests, "
           "exactly one succeeds — enforced by a single atomic conditional "
           "update, not by read-then-write timing.")
synthetic_note()
demo_scope_note()

st.markdown("### The atomic guard")
st.code(
    '// one conditional update on the shared counter document\n'
    'updateOne(\n'
    '  { accountId, capType: "local_tn",\n'
    '    activeCount: { $lte: cap - requestedCount } },\n'
    '  { $inc: { activeCount: requestedCount } }\n'
    ')\n'
    '// missing match ⇒ cap exceeded → reject, save nothing, audit',
    language="javascript")

st.markdown("### Run the race")
c1, c2 = st.columns(2)
with c1:
    if st.button("Reset race account to 99/100", key="reset"):
        from lib.ui import db as cached_db
        seed_demo(cached_db())
        set_counter_for_demo(cached_db(), RACE_ACCOUNT_ID, 99,
                             DEFAULT_CAP)
        st.session_state["race_ready"] = True
        st.success(f"`{RACE_ACCOUNT_ID}` counter set to 99 of "
                   f"{DEFAULT_CAP} (synthetic, demo database only).")
with c2:
    run = st.button("Run two concurrent one-number requests", key="run",
                    disabled=not st.session_state.get("race_ready"))

if run:
    from lib.ui import db as cached_db

    def worker(i: int) -> BatchResult:
        return process_ingest(
            cached_db(), RACE_ACCOUNT_ID,
            [{"tn": FICTIONAL_TNS[50 + i], "type": "local"}],
            f"race-{i}", cap=DEFAULT_CAP,
            idempotency_key=f"race-run-{i}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))

    wins = [r for r in results if r.accepted]
    losses = [r for r in results if not r.accepted]
    st.markdown("#### Outcome")
    st.markdown(f"Request A: "
                f"{ok_badge('202 ACCEPTED') if results[0].accepted else err_badge(CAP_EXCEEDED)}"
                f" · Request B: "
                f"{ok_badge('202 ACCEPTED') if results[1].accepted else err_badge(CAP_EXCEEDED)}")
    if len(wins) == 1 and len(losses) == 1:
        st.success("Exactly one succeeded, one was rejected — the atomic "
                   "condition can only ever match once.")
    else:
        st.error("Unexpected outcome — see results below.")
    for r in results:
        for item in r.results:
            st.caption(f"channel=`{r.channel}` · `{item.tn}` → {item.code} "
                       f"· {item.detail}")
    counter = cached_db()["provisioningCounters"].find_one(
        {"accountId": RACE_ACCOUNT_ID, "capType": CAP_TYPE})
    st.metric("Counter after the race", f"{counter['activeCount']} / {counter['cap']}")
    st.caption("The counter moved 99 → 100 exactly once, and no number was "
               "saved for the rejected request (it can only be verified in "
               "the Results & audit page).")

st.markdown("### Why it is repeatable and safe")
st.markdown(
    "- The guard is a single conditional `updateOne`; MongoDB evaluates the "
    "filter and the `$inc` atomically per document, so a second request that "
    "would exceed the cap finds no match regardless of timing.\n"
    "- The reset button restores the 99/100 state on demand — a targeted "
    "write to the demo database only, never a reseed that deletes anything.\n"
    "- Rejected requests save **no** number asset and record a "
    "`PROVISIONING_REJECTED` audit event instead of queuing.")
