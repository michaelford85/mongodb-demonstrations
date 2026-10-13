# Atlas on Azure — Resilience and Scalability Test Plan

An evidence-based test plan for an existing, non-production MongoDB Atlas cluster deployed on Microsoft Azure, plus the harness used to collect the evidence.

The plan answers three questions the target team raised:

| # | Question | Approach |
|---|---|---|
| Q1 | When a node is lost or replaced, is its storage reattached, or does the replacement perform a full initial sync? | Identify the storage class in use, then observe a node replacement and check for initial-sync evidence in Atlas events and cluster metrics. |
| Q2 | Does sustained or bursty write load destabilise the replica set or lengthen elections? | Measure election duration and client-visible write unavailability at idle, then repeat under paced load and under saturation. |
| Q3 | Will the current data model shard cleanly if the workload outgrows one replica set? | Sample real query traffic with `configureQueryAnalyzer`, then score candidate shard keys with `analyzeShardKey` — before committing to sharding. |

Every result is recorded as a run artefact under `results/` so the numbers in the report can be traced back to a specific run.

---

## Scope and safety

- **Non-production only.** The plan triggers elections and, in one case, a rolling node replacement. Run it against the test cluster and nothing else.
- **No destructive operations against existing data.** All scripts read and write inside a single database (`TEST_DB`, default `resilience_test`) and `teardown.py` drops only that database.
- **Change control.** Test cases T3 through T6 restart cluster processes. Get the change window approved before starting, and confirm no maintenance or scheduled scaling overlaps it.
- **One variable per run.** Do not change tier, disk, load profile, or region layout inside a run. Re-baseline between test cases.
- **Credentials.** Connection string and Atlas API keys live in `.env` only. No script accepts a secret as a command-line argument, so nothing lands in shell history or process listings. Use a Project Read Only API key for evidence collection; a Project Cluster Manager key is needed only to trigger failover from the API instead of the UI.
- **Stop conditions.** Abort the run and record why if: the cluster enters a state other than `IDLE` unexpectedly, replication lag exceeds 60 s, disk usage crosses 80 %, or any write error appears that is not a transient failover error.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | `python -m venv .venv && source .venv/bin/activate` |
| Test cluster on Azure | Dedicated tier (M10 or above). Shared tiers do not expose `replSetGetStatus` or Test Failover. Provision with [`../atlas-cluster-provisioning`](../atlas-cluster-provisioning/) using `CLUSTER_CLOUD_PROVIDER=AZURE`, or point at an existing test cluster. |
| Database users | The provisioner creates all three: `DB_APP_USER` (`readWriteAnyDatabase`) for the load scripts, `DB_MONITOR_USER` (`clusterMonitor`) for topology reads, `DB_ADMIN_USER` (`atlasAdmin`) for T7. |
| Atlas API key | Project Read Only for baseline and event export. |
| Network access | Test runner's egress IP in the project access list. |
| Free disk | At least 5 % free on every node — Atlas blocks Test Failover otherwise. |

```bash
cd atlas-azure-resilience-testing
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — connection string, project ID, cluster name, API key
python3 baseline.py          # confirms connectivity and records the starting state
```

`TEST_CLUSTER_URI` is the only required connection string. Setting the optional `MONITOR_CLUSTER_URI` and `ADMIN_CLUSTER_URI` splits the harness across the three provisioned users so each script connects with the least privilege it needs; both fall back to `TEST_CLUSTER_URI` when unset. Note that `readWriteAnyDatabase` alone cannot run `replSetGetStatus`, so a single-user `.env` has to use the admin or monitor user for the whole harness.

---

## What gets measured

Three independent timelines are captured for each test case and correlated afterwards by UTC timestamp:

| Source | Script | Evidence it provides |
|---|---|---|
| Client | `writer.py` | Per-attempt write outcome and latency; longest interval with no acknowledged write (client-visible write unavailability); missing or duplicate sequence numbers (lost or unexpectedly durable writes). |
| Data plane | `watcher.py` | Primary identity, per-member state, and every interval with no primary (the election window). |
| Control plane | `atlas_events.py` | Atlas project events — elections, host state changes, restarts, cluster updates — which distinguish a process restart from a node replacement. |
| Load | `load_harness.py` | Throughput and p50/p95/p99 latency in 10-second windows, so a failover shows up as a window rather than being averaged away. |

Atlas UI metrics to capture as screenshots alongside each run: **Replication Lag**, **Replication Oplog Window**, **Opcounters**, **Disk IOPS**, **Disk Latency**, **Normalized System CPU**, and **Network** on all three nodes.

---

## Test cases

Each case lists the steps, the evidence to keep, and the pass criterion. "Pass" here means the observation is consistent with the documented behaviour — not that the cluster is fast enough for any particular application SLA.

### T1 — Baseline and storage class identification (read-only)

1. `python3 baseline.py`
2. In the artefact, read `controlPlane.replicationSpecs[].regionConfigs[].electableSpecs.instanceSize` and `diskIOPS`.
3. Classify the storage: an `_NVME` suffix on the instance size means locally attached ephemeral NVMe SSD; anything else on a dedicated Azure tier is network-attached Azure Premium SSD. If the cluster came from `../atlas-cluster-provisioning`, this should agree with `CLUSTER_STORAGE_CLASS` in that folder's `.env` — a mismatch means the cluster drifted from its Terraform state.
4. Record the Oplog Window from the Atlas UI (**Metrics → Replication Oplog Window**) — it bounds how long a node can be absent and still catch up without a full resync.

**Pass:** storage class, disk size, IOPS, tier, region layout, MongoDB version, and oplog window are all recorded. This case cannot fail; it establishes the reference state.

### T2 — Idle election baseline

1. Start `python3 watcher.py --label t2-idle` and `python3 writer.py --label t2-idle` in separate terminals.
2. Let both run for 5 minutes with no other load.
3. Trigger **Test Primary Failover** from the Atlas UI (cluster **...** menu) or the Administration API.
4. Wait until `watcher.py` reports a new primary and `writer.py` resumes acknowledging writes. Continue for 5 more minutes, then stop both with Ctrl+C.
5. `python3 atlas_events.py --since-minutes 20 --label t2-idle`

**Evidence:** watcher summary (longest interval with no primary), writer summary (longest acknowledgement gap, missing sequence numbers), event timeline.

**Pass:** exactly one primary at the end; zero missing sequence numbers; the acknowledgement gap is bounded and recorded. This gap is the control value that T4 and T5 are compared against.

### T3 — Repeated elections at idle

1. Repeat T2 three times, at least 10 minutes apart, labels `t3-idle-1` … `t3-idle-3`.
2. After each iteration confirm the cluster returns to `IDLE` and replication lag returns to baseline before starting the next.

**Evidence:** three watcher and writer summaries, plus one event export per iteration.

**Pass:** election windows are consistent across iterations (no upward trend), no missing sequence numbers in any iteration, and no `TOO_MANY_ELECTIONS` event.

### T4 — Election under paced load

1. Start `watcher.py --label t4-load` and `writer.py --label t4-load`.
2. Start `python3 load_harness.py --profile steady --duration 900 --label t4-load`.
3. Let load run 5 minutes, then trigger Test Primary Failover.
4. Let the run finish, stop the watcher and writer, then `python3 atlas_events.py --since-minutes 30 --label t4-load`.

**Evidence:** load windows either side of the failover, watcher and writer summaries, event timeline, UI metrics screenshots.

**Pass:** the election window is within the same order of magnitude as T2; zero missing sequence numbers; throughput and p99 latency return to the pre-failover window values after recovery. A materially longer election than T2 is itself a finding — record it rather than retrying until it looks better.

### T5 — Election under saturation

1. As T4, but `python3 load_harness.py --profile saturate --duration 600 --label t5-saturate`.
2. Before triggering failover, confirm from the Atlas UI that CPU and disk latency are elevated but replication lag is still under 10 s — Atlas refuses Test Failover above that.
3. Trigger Test Primary Failover, let the run complete, and export events.

**Evidence:** as T4, plus the peak lag and CPU observed at the moment of failover.

**Pass:** no missing sequence numbers; the cluster returns to a single primary without operator intervention. Longer acknowledgement gaps than T4 are expected under saturation and should be quantified, not treated as failure.

### T6 — Node replacement and storage reuse (Support-assisted for the true-loss variant)

Atlas does not expose a customer-triggered "terminate a node" action. Two variants are available; run T6a self-service, and request T6b only if the target team needs the true node-loss answer.

**T6a — rolling replacement (self-service).** A tier or disk change causes Atlas to replace cluster nodes one at a time.

1. `python3 baseline.py`, then start `watcher.py --label t6a` and `writer.py --label t6a`.
2. Apply a small, reversible change and note the start time. If the cluster came from `../atlas-cluster-provisioning`, raise `CLUSTER_DISK_SIZE_GB` to the next Azure-supported size and re-run `./deploy.sh`, which keeps the change in version control; otherwise increase disk size by the smallest allowed increment in the Atlas UI.
3. Watch each member cycle through `SECONDARY` → absent → `STARTUP2`/`RECOVERING` → `SECONDARY`. Record how long each member is not in `SECONDARY` or `PRIMARY`.
4. When the cluster returns to `IDLE`: `python3 atlas_events.py --since-minutes 120 --label t6a`.
5. In the Atlas UI, check each replaced node's **Network — bytes in** and **Disk — space used** during its recovery window. A full initial sync moves the whole data set over the network and rebuilds the volume from empty; a catch-up from the oplog does not.
6. Revert the change and confirm the cluster returns to `IDLE`.

**T6b — simulated node loss (Support-assisted).** Open a Support case describing the test cluster, the goal (observe whether a replacement node reuses its Azure Premium SSD or performs an initial sync), and the approved window. Ask Support to confirm what the platform actually does for the tier in use, and whether they can demonstrate it on the test cluster.

**Evidence:** per-member out-of-service duration, event timeline showing whether the host name changed, bytes-in and disk-used curves during recovery, plus any written confirmation from Support.

**Pass:** the cluster stays writable throughout (writer.py records no missing sequence numbers); every member returns to `SECONDARY` or `PRIMARY`; and the run produces enough evidence to state whether an initial sync occurred, or to state clearly that it could not be determined.

### T7 — Shard-key readiness on the current data model (read-mostly)

Runs on the unsharded replica set. Nothing is sharded as part of this plan.

1. Choose the namespace that would be sharded first. `resilience_test.load_events` works as a rehearsal; a copy of a representative application collection gives a more useful answer.
2. Enable sampling and leave representative traffic running:
   ```bash
   python3 shard_key_analysis.py --namespace <db>.<coll> --enable-sampling --sample-rate 5
   ```
3. Run the workload — `load_harness.py --profile steady`, or the application's own read/write mix — for at least 30 minutes.
4. Score two or three candidate keys:
   ```bash
   python3 shard_key_analysis.py --namespace <db>.<coll> \
       --key customer_id:hashed --key customer_id:1,created_at:1
   ```
5. Disable sampling:
   ```bash
   python3 shard_key_analysis.py --namespace <db>.<coll> --disable-sampling
   ```

**Evidence:** the analysis artefact for each candidate — distinct values, most-common-value frequency, monotonicity, and the read/write distribution percentages.

**Pass:** at least one candidate has high cardinality, low most-common-value frequency, no monotonic trend, and a high single-shard read percentage. If no candidate qualifies, that is the finding: the model needs a change before sharding, not a bigger cluster.

### T8 — Premium SSD vs. local NVMe comparison (optional, second cluster)

Only worth running if the target team is weighing local NVMe for the write throughput. It answers Q1 directly by making the two storage classes observable side by side, rather than inferring one from the other.

1. Provision a second cluster with `../atlas-cluster-provisioning`, identical to the first except `CLUSTER_STORAGE_CLASS=NVME`. On Azure, local NVMe starts at M60, so this cluster is materially more expensive than the SSD baseline — confirm the spend and plan to tear it down the same day.
2. Note two consequences the provisioner enforces: `CLUSTER_DISK_SIZE_GB` must be `0` (Atlas fixes NVMe capacity per tier), and Compute Auto-Scale is skipped, since Atlas does not auto-scale the local NVMe class. Neither affects the failover measurements, but both belong in the report as constraints of the option.
3. Point `.env` at the NVMe cluster and run T1, T2, and T4.
4. Run T6a against it, using a tier change to force the rolling replacement — the disk-size route is unavailable, since NVMe capacity is fixed per tier. Because local NVMe is ephemeral, a replaced node must be rebuilt by initial sync, so this is where the two storage classes should visibly diverge in recovery time and bytes-in.
5. Tear down the NVMe cluster with `../atlas-cluster-provisioning/teardown.sh` once the artefacts are collected.

**Evidence:** T1, T2, T4 and T6a artefacts from both clusters, kept under distinct labels (`ssd-*` and `nvme-*`).

**Pass:** the comparison is recorded with matched tiers and load profiles. If the tiers cannot be matched — because Azure's NVMe floor is above the SSD cluster's tier — say so, and treat the throughput difference as tier-plus-storage rather than storage alone.

---

## Reporting template

One row per run, filled in from the script summaries. Keep the raw artefacts alongside it.

| Test | Run label | Election window (s) | Client write gap (s) | Missing seqs | Duplicate seqs | Notes |
|---|---|---|---|---|---|---|
| T2 | `t2-idle` | | | | | |
| T3 | `t3-idle-1..3` | | | | | |
| T4 | `t4-load` | | | | | |
| T5 | `t5-saturate` | | | | | |
| T6a | `t6a` | n/a | | | | per-member recovery time |
| T8 | `nvme-*` | | | | | optional; repeat the rows above per cluster |

Throughput and latency, from `load_harness.py` windows:

| Test | Window | Writes/s | Write p95 (ms) | Write p99 (ms) | Reads/s | Read p95 (ms) | Errors |
|---|---|---|---|---|---|---|---|
| T4 | pre-failover | | | | | | |
| T4 | failover | | | | | | |
| T4 | post-recovery | | | | | | |

---

## Observed facts, documented behaviour, assumptions, open questions

Keep these four categories separate in the report. Only the first is evidence from this cluster.

**Observed facts** — to be filled in from the run. Each entry cites a run label and an artefact file. Examples of what belongs here: the measured election window at idle, the client-visible write gap under load, the storage class and IOPS reported by the control plane, per-member recovery time during a rolling replacement.

**Documented behaviour** — from MongoDB and Microsoft product documentation, not from this run:

- Atlas dedicated clusters on Azure use Azure Premium SSD storage; instance sizes with an `_NVME` suffix use locally attached NVMe SSDs at a fixed capacity per tier. On Azure the local NVMe class starts at M60. See [Atlas on Microsoft Azure](https://www.mongodb.com/docs/atlas/reference/microsoft-azure/) and [Customize storage](https://www.mongodb.com/docs/atlas/customize-storage/).
- Locally attached NVMe storage is ephemeral: a node that loses its local storage must be rebuilt by initial sync from another member.
- Atlas does not offer cluster-tier or disk auto-scaling on the local NVMe class, and disk capacity cannot be set independently of the tier.
- Atlas **Test Primary Failover** steps down the primary so the remaining members hold an election, then restarts the former primary as a secondary. Atlas requires the cluster to have no pending changes, all members healthy, replication lag under 10 seconds, and at least 5 % free disk on every node. See [Test failover](https://www.mongodb.com/docs/atlas/tutorial/test-resilience/test-primary-failover/).
- Writes acknowledged with `w: "majority"` are not rolled back. Writes acknowledged by the primary only can be rolled back if that primary steps down before they replicate.
- `analyzeShardKey` returns read and write distribution metrics only for namespaces that `configureQueryAnalyzer` has been sampling; without sampling those fields are zero. See [analyzeShardKey](https://www.mongodb.com/docs/manual/reference/command/analyzeShardKey/).
- Atlas distributes replica set members across Azure availability zones in regions that provide them.

**Assumptions** — state these explicitly and revisit if the test contradicts them:

- The test cluster's tier, region layout, storage class, and MongoDB version match the production topology the target team cares about. If not, the numbers are indicative only.
- The load profile in `load_harness.py` is a stand-in for the application's read/write mix, not a replica of it.
- The test runner's network path to the cluster is not the bottleneck. Verify by comparing idle write latency to the Atlas UI's own operation latency.
- No Atlas maintenance, auto-scaling event, or index build overlaps a measured window.

**Open questions** — carry forward to the target team or to Support:

- For the Premium SSD tiers, does a replacement node reattach the existing volume, or is it always built by initial sync? Atlas does not document this at the volume level; T6a gives indirect evidence, T6b asks Support directly, and T8 provides the NVMe contrast case where initial sync is the documented outcome.
- What is the target team's acceptable client-visible write unavailability during an election? Without that number, T4 and T5 produce measurements but no pass/fail against a business requirement.
- Which application namespace should T7 analyse? The rehearsal namespace answers the mechanics; only a representative collection answers the design question.
- Is the production workload's growth in data volume, write throughput, or working-set size? Each points to a different scaling response, and only the second and third are solved by sharding.

---

## Checklist

**Before the first run**

- [ ] Cluster confirmed non-production, and the project contains no production cluster.
- [ ] Change window approved; no Atlas maintenance or scheduled scaling inside it.
- [ ] `.env` populated; `.env` confirmed git-ignored; no secret passed on any command line.
- [ ] API key scoped to Project Read Only (or Project Cluster Manager only if triggering failover from the API).
- [ ] Test runner IP in the project access list; `baseline.py` runs cleanly.
- [ ] Disk usage under 80 % and at least 5 % free on every node.
- [ ] Acceptable write-unavailability target agreed, or explicitly recorded as unknown.
- [ ] Owner named for aborting the run if a stop condition is hit.

**After the last run**

- [ ] Cluster state `IDLE`, exactly one primary, replication lag back to baseline.
- [ ] Any tier or disk change made for T6a reverted.
- [ ] Second cluster from T8, if provisioned, torn down via `../atlas-cluster-provisioning/teardown.sh`.
- [ ] `configureQueryAnalyzer` sampling disabled on every namespace it was enabled on.
- [ ] `python3 teardown.py --confirm <TEST_DB>` run to drop the test database.
- [ ] Artefacts collected from `results/`, and screenshots attached to the report.
- [ ] Report separates observed facts, documented behaviour, assumptions, and open questions.
- [ ] Report reviewed for connection strings, host names, API keys, and any identifier that should not be shared externally.

---

## Files

| Path | Purpose |
|---|---|
| `.env.example` | Connection strings (one required, two optional least-privilege), Atlas API key, harness tuning |
| `requirements.txt` | PyMongo, python-dotenv, requests |
| `common.py` | Shared env loading, artefact paths, Atlas Administration API client |
| `baseline.py` | T1 — control-plane and data-plane baseline capture |
| `writer.py` | Monotonic `w=majority` write probe; reports lost writes and write-unavailability window |
| `watcher.py` | Replica set state watcher; reports intervals with no primary |
| `load_harness.py` | Paced or saturating read/write load with per-window latency percentiles |
| `atlas_events.py` | Atlas project event export for a test window |
| `shard_key_analysis.py` | T7 — `configureQueryAnalyzer` sampling and `analyzeShardKey` scoring |
| `teardown.py` | Drops `TEST_DB` only, with an explicit name confirmation |

---

## Notes

- Every script is safe to re-run. `writer.py` continues from the current high-water mark rather than restarting the sequence, so repeated runs build one continuous record.
- `results/` is git-ignored. Artefacts contain host names and cluster names — review before sharing.
- The plan deliberately measures client-visible behaviour as well as server-side state. A short election with a long client stall points at driver or connection-pool configuration, not at the cluster.
