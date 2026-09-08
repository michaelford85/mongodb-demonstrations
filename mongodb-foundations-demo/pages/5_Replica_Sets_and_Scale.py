"""Section ⑤: replica sets, resilience, and a scale callout."""

import streamlit as st

from lib.deployment import (SHARDING_CALLOUT, hello_summary, replset_status,
                            topology_rows)
from lib.ui import (connection_guard, cue, page_header, page_setup,
                    presenter_mode, prose, sidebar_reset, table, takeaway)

page_setup("Replica sets & scale", icon="⑤")
presenter_mode()
connection_guard()
sidebar_reset()

page_header("⑤", "Replica sets, resilience & scale",
            "A read-only summary of the deployment this session is connected to.")

summary = hello_summary()
if not summary["ok"]:
    st.error("Could not read deployment metadata: {}".format(summary["error"]))
    st.stop()

st.markdown("#### What the deployment reports")
metrics = st.columns(3)
metrics[0].metric("Replica set", summary["replica_set"])
metrics[1].metric("Connected member role", summary["connected_member_role"])
metrics[2].metric("Members reported",
                  len(summary["members_reported"]) or "not reported")

table([{"property": "connected member", "value": summary["connected_member"]},
       {"property": "current primary", "value": summary["primary"]},
       {"property": "members", "value": ", ".join(summary["members_reported"])
        or "not reported"}])
st.caption("Source: the `hello` command — available to any authenticated user.")

st.markdown("#### As the driver sees it")
driver_rows = topology_rows()
table(driver_rows, "The driver has not yet discovered any server.")
st.caption("The driver maintains its own view of every member and which one is "
           "primary. That is how it keeps working through an election without "
           "the application changing anything.")

st.markdown("#### Member status")
status = replset_status()
if status["authorized"]:
    table(status["members"])
    st.caption("Source: `replSetGetStatus`. Replication lag is computed against "
               "the primary's optime at the moment of this call.")
else:
    st.info("**Detailed member status is not available to this user.** {}"
            .format(status["note"]))
    st.caption("The `hello` and driver-topology views above are sufficient for "
               "this section — they already show the replica-set name, the "
               "members, and which member is primary.")

st.markdown("---")
st.warning("**Conceptual callout — not this cluster.** {}"
           .format(SHARDING_CALLOUT))

cue("Resilience first, scale second. A replica set is about surviving the loss "
    "of a member; sharding is about distributing data beyond one member's "
    "capacity. They compose, and they solve different problems.")

prose(
    "**What the replica set gives you.** Multiple members hold the same data. "
    "One is the primary and takes writes; the others replicate from its oplog. "
    "If the primary becomes unavailable, the remaining members elect a new one, "
    "and a retryable-writes driver rides through it. Write concern `majority` — "
    "which this demo uses — means a write is acknowledged only once a majority "
    "of members hold it, so an election cannot lose it.\n\n"
    "**Where reads can go.** Reads default to the primary. A read preference "
    "can send them to secondaries, which trades a consistency guarantee for "
    "read capacity — the relevant question is how stale a given read is allowed "
    "to be.\n\n"
    "**On sharding.** Sharding is a horizontal-scale mechanism, chosen when one "
    "member can no longer hold the data or absorb the write rate. The shard key "
    "determines distribution and is the decision that matters most. This "
    "session deliberately does not demonstrate it: the demo deployment is a "
    "single replica set, and showing sharding commands against it would be "
    "misleading.")

takeaway("This is a replica set: durable, self-healing, and the deployment "
         "topology that multi-document transactions require. Sharding is a "
         "separate, additive scale decision.")
