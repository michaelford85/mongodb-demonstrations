# DSN transition timing runbook (operator-executed; not automated)

**Important:** This benchmark's "index build → verified ready" phase measures a
*fresh Atlas Search index build* on a cluster. It does **not** measure the
duration or behavior of enabling or migrating an existing Search workload to
**Dedicated Search Nodes (DSNs)**. Those are different operations with different
durations and impacts. DSN provisioning/migration must be performed separately
in the Atlas UI / Admin API by an authorized operator — this demo intentionally
does **not** call Atlas admin APIs or alter cluster, tier, region, or DSN
topology.

The proposed tier (S10, three-region Azure deployment) is a planning input.
Region-specific S10 specs and exact node count/topology must be verified
separately before recording anything below.

## What the operator records

Record UTC timestamps for every step below in `results/dsn_transition.md`
(copy this template). Use one consistent clock.

| # | Event | UTC timestamp | Notes |
|---|-------|---------------|-------|
| 1 | Pre-change: workload running; note current Search QPS/latency baseline (from this demo's `load` phase or app metrics) | | |
| 2 | Pre-change: record index state (`READY`, `queryable`) via `benchmark.py index` polling output or Atlas UI | | |
| 3 | DSN change submitted in Atlas (separately approved) | | |
| 4 | First observed index state change during transition (Atlas UI > Search tab) | | |
| 5 | Index back to `READY`/queryable, region 1 | | |
| 6 | Index back to `READY`/queryable, region 2 | | |
| 7 | Index back to `READY`/queryable, region 3 | | |
| 8 | First successful representative `$search` query after the change (run `python confirm_search_nodes.py`) | | |
| 9 | Sustained validation: queries succeed for the configured window (`INDEX_VALIDATION_WINDOW_SECONDS`) | | |
| 10 | Per-node/per-region status: record **only** what Atlas UI / Support actually shows, per region (the driver does not expose this) | | |
| 11 | Post-change: repeat `benchmark.py load` baseline; compare achieved QPS + latency vs step 1 | | |

## Required confirmations before you begin

1. **"Ready in each region"** must be defined for your actual Atlas topology
   and monitoring mechanism (e.g. per-region Search Node health in Atlas UI or
   supported monitoring integration). Confirm what Atlas actually reports for
   your deployment before claiming per-region readiness.
2. Confirm the exact S10 spec and node count for each region from current
   MongoDB documentation and your Atlas project — do not assume specs.
3. Confirm the cluster owner has approved the DSN change and an optional
   maintenance window.

## What this runbook cannot prove

- A guaranteed cutover time or zero-downtime guarantee.
- Production availability SLAs.
- That fresh-index build time predicts DSN transition time.

## References (URLs verified reachable at time of writing)

- Deployment options incl. Dedicated Search Nodes and migration: https://www.mongodb.com/docs/search/deployment/deployment-options/
- Monitoring Search: https://www.mongodb.com/docs/search/deployment/monitoring/
- Manage Search indexes (create/poll/drop): https://www.mongodb.com/docs/atlas/atlas-search/manage-indexes/
- `$search` query syntax: https://www.mongodb.com/docs/atlas/atlas-search/query-syntax/
