"""Section ②: querying and aggregation, with two prebuilt examples."""

import streamlit as st
from pymongo.errors import PyMongoError

from lib.queries import (CUSTOMER_PROJECTION, customer_filter, run_customer_filter,
                         run_pipeline, spend_by_category_pipeline,
                         spend_by_customer_pipeline)
from lib.sample_data import CONTACT_CHANNELS, PLACES
from lib.ui import (connection_guard, cue, mql, page_header, page_setup,
                    presenter_mode, prose, seed_guard, sidebar_reset,
                    synthetic_note, table, takeaway)

page_setup("Querying & aggregation", icon="②")
presenter_mode()
connection_guard()
sidebar_reset()
seed_guard()

page_header("②", "Querying & aggregation",
            "Two prebuilt examples: a projected find, and a grouped pipeline.")

STATES = sorted({state for _, state in PLACES})

example_one, example_two = st.tabs(["Example 1 · Filter and project",
                                    "Example 2 · Aggregate transactions"])

with example_one:
    st.markdown("#### Find customers by a nested preference and geography")
    controls = st.columns(2)
    channel = controls[0].selectbox("preferences.contact_channel",
                                    CONTACT_CHANNELS)
    state = controls[1].selectbox("address.state", STATES, index=0)

    st.markdown("**The query**")
    mql({"find": "customers",
         "filter": customer_filter(channel, state),
         "projection": CUSTOMER_PROJECTION})

    if st.button("▶︎ Run example", key="run_find", type="primary"):
        try:
            rows = run_customer_filter(channel, state)
            st.session_state["find_rows"] = rows
        except PyMongoError as exc:
            st.error("Query failed: {}".format(exc))
            st.session_state["find_rows"] = None

    if "find_rows" in st.session_state and st.session_state["find_rows"] is not None:
        rows = st.session_state["find_rows"]
        st.success("{} customer(s) matched.".format(len(rows)))
        table(rows, "No customer prefers '{}' in {}. Try another combination."
                    .format(channel, state))

    st.caption("SQL intent · `SELECT … FROM customers WHERE contact_channel = ? "
               "AND state = ?` — except the predicate reaches into nested "
               "fields with dotted paths, and the projection returns a shaped "
               "document rather than a flat row.")

with example_two:
    st.markdown("#### Aggregate transactions with `$match` and `$group`")
    controls = st.columns(2)
    grouping = controls[0].radio("Group by", ["category", "customer"],
                                horizontal=True)
    days = controls[1].select_slider("Window (days back)", [30, 60, 90, 180],
                                     value=90)

    if grouping == "category":
        pipeline, label = spend_by_category_pipeline(days), "category"
    else:
        pipeline, label = spend_by_customer_pipeline(days), "customer_id"

    st.markdown("**The pipeline**")
    mql(pipeline)

    if st.button("▶︎ Run example", key="run_agg", type="primary"):
        try:
            st.session_state["agg_rows"] = run_pipeline(pipeline, label)
        except PyMongoError as exc:
            st.error("Aggregation failed: {}".format(exc))
            st.session_state["agg_rows"] = None

    if "agg_rows" in st.session_state and st.session_state["agg_rows"] is not None:
        rows = st.session_state["agg_rows"]
        st.success("{} group(s) returned.".format(len(rows)))
        table(rows, "No debit transactions in that window.")

    st.caption("SQL intent · `SELECT {0}, COUNT(*), SUM(amount) FROM "
               "transactions WHERE direction = 'debit' AND posted_at >= ? "
               "GROUP BY {0} ORDER BY SUM(amount) DESC`. `$match` filters, "
               "`$group` aggregates, and stages run in the order you write "
               "them.".format(label))

cue("Read the pipeline top to bottom: filter first, then group, then sort. "
    "Stage order is the execution order, and it is yours to control.")

prose(
    "**Why a pipeline rather than a single statement.** An aggregation pipeline "
    "is an explicit sequence of transformations. Each stage takes documents in "
    "and emits documents out, so the shape of the data at every step is "
    "something you can inspect. That is a different ergonomic from a declarative "
    "SQL statement where the optimiser chooses the order — and it is why "
    "`$match` belongs as early as possible: it is the stage that lets an index "
    "reduce the working set before any grouping happens.\n\n"
    "**What is deliberately not here.** No text search, vector search, "
    "geospatial, `$graphLookup`, or time-series examples. Those are separate "
    "conversations and would dilute the foundations.")

takeaway("`find` with projection covers point and range reads. `$match` + "
         "`$group` covers the GROUP BY workload, with stage order under your "
         "control.")

synthetic_note()
