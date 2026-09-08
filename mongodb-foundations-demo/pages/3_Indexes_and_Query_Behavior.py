"""Section ③: the index list, a compound-index query, and explain stats."""

import streamlit as st
from pymongo.errors import PyMongoError

from lib.mongo_client import TRANSACTIONS
from lib.queries import (explain_statement, index_list, indexed_accounts,
                         run_statement, statement_filter)
from lib.ui import (connection_guard, cue, mql, page_header, page_setup,
                    presenter_mode, prose, seed_guard, sidebar_reset,
                    synthetic_note, table, takeaway)

page_setup("Indexes & query behaviour", icon="③")
presenter_mode()
connection_guard()
sidebar_reset()
seed_guard()

page_header("③", "Indexes & query behaviour",
            "The indexes on `{}`, and what `explain` reports for a query that "
            "uses one.".format(TRANSACTIONS))

st.markdown("#### Indexes on `{}`".format(TRANSACTIONS))
try:
    table(index_list(TRANSACTIONS))
except PyMongoError as exc:
    st.error("Could not list indexes: {}".format(exc))

st.caption("`_id_` is created automatically. The two compound indexes exist "
           "for this demo's access patterns: account statements, and "
           "category aggregation.")

st.markdown("---")
st.markdown("#### A query the compound index serves")

accounts = indexed_accounts()
controls = st.columns(2)
account = controls[0].selectbox("account_number", accounts)
days = controls[1].select_slider("Window (days back)", [30, 60, 90, 180],
                                 value=90)

mql({"find": TRANSACTIONS, "filter": statement_filter(account, days),
     "sort": {"posted_at": -1}, "limit": 25})
st.caption("Equality on `account_number`, then a range and a sort on "
           "`posted_at` — the exact shape of the index "
           "`account_number_1_posted_at_-1`.")

if st.button("▶︎ Run query", type="primary"):
    try:
        st.session_state["stmt_rows"] = run_statement(account, days)
    except PyMongoError as exc:
        st.error("Query failed: {}".format(exc))
        st.session_state["stmt_rows"] = None

if st.session_state.get("stmt_rows"):
    table(st.session_state["stmt_rows"])
elif st.session_state.get("stmt_rows") == []:
    st.warning("No transactions for that account in that window.")

st.markdown("---")
st.markdown("#### `explain` in execution-stats mode")
st.caption("Runs the same query twice: once as the planner chooses it, and once "
           "hinted to `$natural` so it must scan. No index is dropped, and "
           "nothing is written.")

if st.button("🔍 Run explain (execution stats)"):
    try:
        st.session_state["explain"] = {
            "indexed": explain_statement(account, days),
            "scan": explain_statement(account, days,
                                      force_collection_scan=True),
        }
    except PyMongoError as exc:
        st.error("`explain` failed: {}".format(exc))
        st.session_state["explain"] = None

result = st.session_state.get("explain")
if result:
    fields = ["plan", "index_used", "keys_examined", "documents_examined",
              "documents_returned", "execution_time_ms"]
    rows = [{"metric": f.replace("_", " "),
             "with index": result["indexed"].get(f),
             "forced collection scan": result["scan"].get(f)}
            for f in fields]
    table(rows)
    st.caption("Values are from this run on this deployment. Treat them as an "
               "illustration of the access pattern, not a benchmark — a warm "
               "cache, a small collection, and network variance all move the "
               "timing.")
    with st.expander("The exact command that was explained"):
        mql(result["indexed"]["command"])

cue("Compare documents examined against documents returned. Closing that gap "
    "is what an index does.")

prose(
    "**Reading the plan.** `IXSCAN` means the index supplied the candidate keys; "
    "`FETCH` means the server then loaded the documents; `COLLSCAN` means every "
    "document was examined. When `keys examined` and `documents returned` are "
    "close, the index is doing the selection work. When `documents examined` is "
    "far larger than `documents returned`, the query is filtering after reading.\n\n"
    "**Compound index order matters.** The prefix rule is familiar from "
    "relational indexing: equality fields first, then the range or sort field. "
    "`{account_number: 1, posted_at: -1}` serves an equality on account plus a "
    "sorted range on time. Reverse the order and the same query no longer gets "
    "a sorted result for free.\n\n"
    "**The trade-off.** Every index has to be maintained on insert, update, and "
    "delete, and it consumes storage and cache. Indexes buy read efficiency with "
    "write throughput and memory. This demo creates five, each tied to a query "
    "shown in the session — that is the discipline to carry into production.")

takeaway("`explain` in execution-stats mode is the primary tool: check the "
         "winning plan's stage, then the ratio of documents examined to "
         "documents returned.")

synthetic_note()
