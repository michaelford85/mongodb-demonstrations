"""Section ⑥: the monitoring handoff — general MongoDB, not Atlas UI steps."""

import streamlit as st

from lib.ui import (cue, page_header, page_setup, presenter_mode, prose,
                    sidebar_reset, table, takeaway)

page_setup("Monitoring handoff", icon="⑥")
presenter_mode()
sidebar_reset()

page_header("⑥", "Monitoring handoff",
            "What to inspect in your monitoring tool — whichever tool that is.")

st.markdown("#### What to inspect in your monitoring tool")

SIGNALS = [
    {"Signal": "Replication lag and oplog window / headroom",
     "Question it answers": "Are secondaries able to remain current, and can a "
                            "member that falls behind still catch up from the "
                            "oplog rather than resync?",
     "Why it matters": "Lag is the leading indicator of a member under strain, "
                       "and the oplog window is the recovery budget."},
    {"Signal": "Disk latency and IOPS",
     "Question it answers": "Can every member sustain both the application "
                            "workload and replication?",
     "Why it matters": "A secondary is doing the same writes as the primary. "
                       "Storage that is adequate for one is not automatically "
                       "adequate for all."},
    {"Signal": "Operation counters",
     "Question it answers": "What actually changed in workload volume and mix — "
                            "queries, inserts, updates, getmores?",
     "Why it matters": "Separates a workload change from a capacity problem "
                       "before you resize anything."},
]
table(SIGNALS)

cue("Next, switch to Atlas to show these same concepts as live metrics. The "
    "metrics and operational questions apply to MongoDB deployments generally; "
    "the UI is Atlas-specific.")

prose(
    "**Why these three, in this order.** Replication lag and oplog headroom tell "
    "you whether the resilience you designed still holds right now — a replica "
    "set with a lagging secondary has less redundancy than the topology diagram "
    "suggests. Disk latency and IOPS tell you whether the members can physically "
    "keep up, and it is the metric most often under-provisioned on secondaries "
    "because they are assumed to be idle. Operation counters tell you whether "
    "something changed in the workload, which is the question to answer before "
    "concluding that the deployment needs to be bigger.\n\n"
    "**The habit to carry over from relational operations.** The instincts "
    "transfer directly: watch the write-ahead path, watch storage latency, and "
    "correlate against workload volume before resizing. The names differ — oplog "
    "rather than redo log, replica-set members rather than standbys — but the "
    "operational reasoning is the same.\n\n"
    "**Tool-independent by design.** This panel names signals, not screens. Any "
    "monitoring stack that can read MongoDB server metrics can answer these "
    "questions; Atlas is simply the one in front of us today.")

takeaway("Three questions cover most of it: are secondaries current, can every "
         "member sustain the workload, and what changed in the workload?")

st.markdown("---")
st.caption("This section is intentionally static — it is the handoff to the "
           "live monitoring GUI, not a second monitoring dashboard.")
