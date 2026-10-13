"""Section ⑤: what a replica set is, mapped to relational vocabulary."""

import streamlit as st

from lib.deployment import (SHARDING_CALLOUT, hello_summary,
                            member_configuration, replset_status,
                            topology_rows)
from lib.ui import (connection_guard, cue, page_header, page_setup,
                    presenter_mode, prose, sidebar_reset, table, takeaway)

page_setup("Replica sets", icon="⑤")
presenter_mode()
connection_guard()
sidebar_reset()

page_header("⑤", "Replica sets — an overview",
            "What a replica set is, and a read-only look at the one this "
            "session is connected to.")

# The relational mapping is the fastest way in for this audience: the mechanism
# is familiar, only the names differ.
MAPPING = [
    {"Replica set concept": "Primary",
     "Closest relational idea": "Read/write instance",
     "Note": "Exactly one member accepts writes at any time."},
    {"Replica set concept": "Secondary",
     "Closest relational idea": "Physical standby / replica",
     "Note": "Holds a full copy of the data and applies the same writes."},
    {"Replica set concept": "Oplog",
     "Closest relational idea": "Redo / WAL shipped to standbys",
     "Note": "A capped collection of idempotent operations; secondaries tail "
             "it. Its size sets the catch-up budget."},
    {"Replica set concept": "Election",
     "Closest relational idea": "Failover / role transition",
     "Note": "Automatic and built in — no external cluster manager, no "
             "scripted promotion."},
    {"Replica set concept": "Majority",
     "Closest relational idea": "Quorum",
     "Note": "More than half the voting members. Needed to elect a primary "
             "and to acknowledge a `majority` write."},
]

st.markdown("#### Replica-set vocabulary, in relational terms")
table(MAPPING)

st.markdown("#### What this deployment reports")
summary = hello_summary()
if not summary["ok"]:
    st.error("Could not read deployment metadata: {}".format(summary["error"]))
    st.stop()

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
table(topology_rows(), "The driver has not yet discovered any server.")
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

st.markdown("#### Member configuration")
config = member_configuration()
if config["authorized"]:
    table(config["members"])
    st.caption("Voting members: {} · a majority is {}. `priority` decides which "
               "members are eligible to be elected; `votes` decides which "
               "members count towards that majority."
               .format(config["voting_members"], config["majority_size"]))
else:
    st.info("**Member configuration is not available to this user.** {}"
            .format(config["note"]))

st.markdown("---")
st.warning("**Conceptual callout — not this cluster.** {}"
           .format(SHARDING_CALLOUT))

cue("A replica set is about surviving the loss of a member. Sharding is about "
    "distributing data beyond one member's capacity. They compose, and they "
    "solve different problems — this is the first, section ⑥ is what it buys "
    "you operationally.")

prose(
    "**What a replica set is.** A group of `mongod` processes holding the same "
    "data. One member is the primary and accepts all writes; the others "
    "replicate by tailing the primary's oplog. Membership, roles, and the "
    "failover mechanism are properties of the deployment itself, not of an "
    "add-on product — a replica set is the normal way to run MongoDB, not an "
    "advanced configuration.\n\n"
    "**Three members is the usual minimum.** Not because three copies of the "
    "data are needed, but because a majority of three survives the loss of one "
    "member. An even number of voting members gains no availability and can "
    "make a majority harder to reach; where a third data-bearing member is not "
    "wanted, an arbiter can vote without holding data — at the cost of losing "
    "a copy, which is why it is a last resort rather than a default.\n\n"
    "**Why the oplog matters more than it first appears.** It is idempotent and "
    "capped. Idempotent means a secondary can re-apply operations safely; "
    "capped means there is a finite window in which a member that falls behind "
    "can still catch up. Beyond that window, the member needs a full resync — "
    "the same reasoning as an archived-log gap in a relational standby.\n\n"
    "**On sharding.** Sharding is horizontal scale, chosen when one member can "
    "no longer hold the data or absorb the write rate; the shard key is the "
    "decision that matters most. This session deliberately does not demonstrate "
    "it: the demo deployment is a single replica set, and running sharding "
    "commands against it would be misleading. Each shard in a sharded cluster "
    "is itself normally a replica set, so nothing on this page is superseded.")

takeaway("A replica set is the default MongoDB deployment: multiple members, "
         "one primary, an oplog, and an automatic election. It is also the "
         "topology multi-document transactions require.")
