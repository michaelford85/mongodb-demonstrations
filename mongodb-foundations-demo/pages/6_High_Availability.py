"""Section ⑥: high availability — elections, durability, and what the app sees."""

import streamlit as st

from lib.deployment import durability_settings, election_summary
from lib.ui import (connection_guard, cue, page_header, page_setup,
                    presenter_mode, prose, sidebar_reset, table, takeaway)

page_setup("High availability", icon="⑥")
presenter_mode()
connection_guard()
sidebar_reset()

page_header("⑥", "High availability & MongoDB",
            "How a replica set survives failure, and which settings decide "
            "what the application experiences.")

st.markdown("#### Election state of this deployment")
election = election_summary()
if election["authorized"]:
    metrics = st.columns(3)
    metrics[0].metric("Current primary", election["primary"] or "not reported")
    metrics[1].metric("Election term", election["term"])
    metrics[2].metric("Majority size", election["majority_size"])
    table([{"property": "primary elected at",
            "value": str(election["elected_at"] or "not reported")},
           {"property": "reason for last election",
            "value": election["election_reason"]}])
    st.caption("Source: `replSetGetStatus`. The term increments with every "
               "successful election, so it is a cheap way to see whether the "
               "deployment has failed over.")
else:
    st.info("**Election detail is not available to this user.** {}"
            .format(election["note"]))

st.markdown("#### What this application's driver is configured to do")
table(durability_settings(), "Driver options are not available.")
st.caption("Read from the connected driver, not from the connection string. No "
           "credential is read or displayed.")

# Each row is a failure the audience will ask about. Kept to what a replica set
# genuinely covers, so nothing here overstates the guarantee.
SCENARIOS = [
    {"Failure": "A secondary is lost",
     "What the deployment does": "Nothing to elect. Writes continue on the "
                                 "primary as long as a majority remains.",
     "What the application sees": "Nothing, unless it was reading from that "
                                  "secondary."},
    {"Failure": "The primary is lost",
     "What the deployment does": "The remaining members detect it, and a "
                                 "majority elects a new primary — typically "
                                 "within seconds.",
     "What the application sees": "A brief window with no writable primary. "
                                  "Retryable writes and server selection "
                                  "absorb it without an application change."},
    {"Failure": "A majority is lost",
     "What the deployment does": "No primary can be elected. The surviving "
                                 "members stay secondary to protect "
                                 "consistency.",
     "What the application sees": "Writes fail rather than diverge. This is a "
                                  "deliberate choice, not a defect."},
    {"Failure": "Planned maintenance on the primary",
     "What the deployment does": "`replSetStepDown` hands over deliberately, "
                                 "at a chosen moment.",
     "What the application sees": "The same short failover window — during a "
                                  "maintenance slot rather than an incident."},
    {"Failure": "Bad data written by the application",
     "What the deployment does": "Replicates it faithfully to every member.",
     "What the application sees": "Corruption everywhere. Replication is not "
                                  "backup; point-in-time restore is a separate "
                                  "requirement."},
]

st.markdown("#### Failure scenarios")
table(SCENARIOS)

cue("Availability is a property of the deployment; the guarantee the "
    "application gets is a property of write concern, read preference, and "
    "retryable writes. The topology alone does not decide it.")

prose(
    "**Automatic failover, in one sentence.** Members heartbeat each other; if "
    "the primary stops responding, the remaining members hold an election, and "
    "a candidate that can reach a majority and has the most recent oplog "
    "becomes the new primary. There is no external clusterware, no virtual IP, "
    "and no scripted promotion to maintain.\n\n"
    "**Write concern is the durability dial.** `w: 1` acknowledges once the "
    "primary has the write — which an election can still lose. `w: majority` "
    "acknowledges only once a majority of members hold it, which makes the "
    "write durable across a failover. That is what this demo uses, and it is "
    "the setting to reach for by default.\n\n"
    "**Read preference is the availability/consistency dial.** Primary reads "
    "are consistent. Secondary reads add read capacity and can survive a "
    "primary outage for read-only traffic, but they may be stale. The useful "
    "question is never 'can I read from a secondary?' — it is 'how stale may "
    "this particular read be?'\n\n"
    "**Retryable writes close the last gap.** During an election there is a "
    "short period with no primary. A driver with retryable writes enabled — the "
    "default in modern drivers — retries the operation once, and the server "
    "guarantees it is not applied twice. Combined with the driver's server "
    "selection timeout, a routine failover becomes latency rather than an "
    "error.\n\n"
    "**Where members sit matters.** Spreading members across independent "
    "failure domains — racks, availability zones, or regions — is what turns "
    "member redundancy into infrastructure redundancy. The trade-off is "
    "latency: a `majority` write is only as fast as the second-fastest member "
    "that must acknowledge it.\n\n"
    "**What HA does not cover.** Replication protects against losing a member. "
    "It does not protect against a bad deployment, an incorrect update, or a "
    "dropped collection — those replicate perfectly. Backups and point-in-time "
    "recovery remain a separate design decision.")

takeaway("A replica set gives automatic failover with no external tooling. "
         "`majority` write concern, a deliberate read preference, and retryable "
         "writes are what turn that into an application that does not notice.")

st.markdown("---")
st.caption("This section is read-only. Nothing here steps down a member, "
           "reconfigures the set, or changes any deployment setting.")
