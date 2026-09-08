"""Section ④: multi-document transactions and consistency."""

import streamlit as st
from pymongo.errors import PyMongoError

from lib.sample_data import TRANSFER_SOURCE, TRANSFER_TARGET
from lib.seed import reset_transaction_demo
from lib.transactions import (balances, demo_transfer_history, preview_transfer,
                              run_transfer, transaction_support)
from lib.ui import (connection_guard, cue, mql, page_header, page_setup,
                    presenter_mode, prose, seed_guard, sidebar_reset,
                    synthetic_note, table, takeaway)

page_setup("Transactions & consistency", icon="④")
presenter_mode()
connection_guard()
sidebar_reset()
seed_guard()

page_header("④", "Transactions & consistency",
            "Move money between two dedicated demo accounts and write the "
            "matching ledger entry — all or nothing.")

support = transaction_support()
if support["available"]:
    st.success(support["reason"])
else:
    st.error("**Transactions are not available here.** {}"
             .format(support["reason"]))
    st.info("The rest of this page still explains the model. Use the sidebar "
            "reset if balances look unexpected.")

st.markdown("#### Balances now")
try:
    table(balances(), "The two demo accounts are missing — reset demo data.")
except PyMongoError as exc:
    st.error("Could not read balances: {}".format(exc))

controls = st.columns([2, 2, 3])
amount = controls[0].number_input("Amount", min_value=1.0, max_value=2000.0,
                                  value=250.0, step=25.0)
direction = controls[1].radio(
    "Direction",
    ["{} → {}".format(TRANSFER_SOURCE, TRANSFER_TARGET),
     "{} → {}".format(TRANSFER_TARGET, TRANSFER_SOURCE)])
reverse = direction.startswith(TRANSFER_TARGET)

preview_col, run_col, reset_col = st.columns(3)

if preview_col.button("👁 Preview transaction", use_container_width=True):
    st.session_state["txn_preview"] = preview_transfer(amount, reverse)
    st.session_state["txn_result"] = None

if run_col.button("▶︎ Run transaction", type="primary",
                  use_container_width=True,
                  disabled=not support["available"]):
    st.session_state["txn_confirm"] = True

if reset_col.button("↺ Reset demo data", use_container_width=True):
    try:
        outcome = reset_transaction_demo()
        st.session_state["txn_result"] = None
        st.session_state["txn_preview"] = None
        st.success("Seed state restored · {} demo ledger entries removed."
                   .format(outcome["demo_transfers_removed"]))
    except PyMongoError as exc:
        st.error("Reset failed: {}".format(exc))

if st.session_state.get("txn_preview"):
    plan = st.session_state["txn_preview"]
    st.markdown("#### Intended operations (nothing has been written)")
    table(plan["operations"])
    st.caption(plan["invariant"])

if st.session_state.get("txn_confirm"):
    st.warning("**Confirm:** write {:.2f} from `{}` to `{}` and insert one "
               "ledger entry, inside one transaction."
               .format(amount, TRANSFER_TARGET if reverse else TRANSFER_SOURCE,
                       TRANSFER_SOURCE if reverse else TRANSFER_TARGET))
    confirm, cancel = st.columns(2)
    if confirm.button("Yes — commit", type="primary", use_container_width=True):
        st.session_state["txn_confirm"] = False
        try:
            st.session_state["txn_result"] = run_transfer(amount, reverse)
        except PyMongoError as exc:
            st.session_state["txn_result"] = {
                "committed": False, "kind": "driver",
                "reason": str(exc), "before": [], "after": [], "ledger": None}
    if cancel.button("Cancel", use_container_width=True):
        st.session_state["txn_confirm"] = False
        st.rerun()

result = st.session_state.get("txn_result")
if result:
    if result["committed"]:
        st.success("Committed atomically — both balances and the ledger entry "
                   "moved together.")
    elif result["kind"] == "invariant":
        st.error("**Aborted by the invariant.** {} Nothing changed."
                 .format(result["reason"]))
    else:
        st.error("**Transaction did not complete.** {}".format(result["reason"]))
        st.info("Common causes: the deployment is not a replica set, the "
                "database user lacks write permission, or the transaction "
                "exceeded its time limit. The demo data is unchanged.")

    st.markdown("#### Before → after")
    before = {row["account_number"]: row["balance"] for row in result["before"]}
    table([{"account_number": row["account_number"],
            "before": before.get(row["account_number"]),
            "after": row["balance"]} for row in result["after"]])

    if result["ledger"]:
        st.markdown("#### The new ledger entry")
        mql(result["ledger"], language="json")

st.markdown("---")
st.markdown("#### Ledger entries written by this demo")
try:
    table(demo_transfer_history(), "None yet — the demo is in its seed state.")
except PyMongoError as exc:
    st.error("Could not read the ledger: {}".format(exc))

cue("The interesting part is not that it works. It is that the invariant spans "
    "documents, which is precisely when a transaction is the right tool.")

prose(
    "**Three facts, and no more.**\n\n"
    "1. An operation on a single document is atomic. An update that touches "
    "twenty fields and a nested array in one document either fully applies or "
    "does not — no transaction required. A well-modelled document turns many "
    "would-be transactions into single-document writes.\n"
    "2. When an invariant genuinely spans documents — as here, where money "
    "leaving one account must arrive in another and the ledger must agree — "
    "MongoDB provides multi-document ACID transactions with the familiar "
    "semantics: all writes commit, or none do.\n"
    "3. This deployment is a replica set, which is what transactions require. "
    "Transactions also work on sharded deployments.\n\n"
    "**Reversible by design.** The two accounts carry `purpose: "
    "transaction_demo` and are excluded from the seeded history. Every write "
    "the demo makes is flagged, so reset restores the exact seed state.")

takeaway("Single-document writes are atomic by default. Reach for a "
         "multi-document transaction when an invariant genuinely spans "
         "documents — not as the normal way to write.")

synthetic_note()
