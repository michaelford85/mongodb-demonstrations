# MongoDB Atlas — NoSQL Modernization Evaluation Walkthrough

A curated agenda for a single-session evaluation of MongoDB Atlas against a relational-modernization checklist. Each agenda item maps to a self-contained demo already in this repository — this folder exists to sequence them, frame the discussion, and capture the talk-track for the item that is not script-driven.

> All demos run against a single Atlas cluster provisioned with [`../atlas-cluster-provisioning`](../atlas-cluster-provisioning). Assume the cluster is already up and sample datasets are loaded.

---

## Agenda

| # | Topic | Format | Walkthrough |
|---|---|---|---|
| 1 | Automated Data Lifecycle Management | Live demo + Atlas UI | [`../mongodb-walkthrough/online-archive`](../mongodb-walkthrough/online-archive) |
| 2 | Performance & Connection Management | Live demo | [`../mongodb-walkthrough/connection-pooling`](../mongodb-walkthrough/connection-pooling) |
| 3 | Multi-Tenancy & Isolation | Live demo + Atlas UI | [`../mongodb-walkthrough/multi-tenancy`](../mongodb-walkthrough/multi-tenancy) |
| 4 | Regional Deployment | Atlas UI walkthrough | [`../mongodb-walkthrough/multi-region`](../mongodb-walkthrough/multi-region) + [`../mongodb-walkthrough/vpc-peering`](../mongodb-walkthrough/vpc-peering) |
| 5 | Addressing Data Modeling Lift | Talk-through (no demo) | [`../mongodb-walkthrough/data-modeling`](../mongodb-walkthrough/data-modeling) + notes below |

---

## Prerequisites

- Cluster from [`../atlas-cluster-provisioning`](../atlas-cluster-provisioning), already running
- Sample datasets loaded (Atlas UI → cluster → `...` → *Load Sample Dataset*)
- Atlas API key with Project Owner role (used by `setup_*.py` scripts in the walkthroughs)
- Each walkthrough has its own `requirements.txt` — install before the session

### Recommended cluster topology for this session

To support the Regional Deployment discussion live, provision the cluster across the two regions raised on the call. Set in `atlas-cluster-provisioning/.env` before `./deploy.sh`:

```env
CLUSTER_CLOUD_PROVIDER=AWS
CLUSTER_INSTANCE_SIZE=M30
CLUSTER_NUM_REGIONS=2
CLUSTER_REGIONS='[
  {"region_name":"AP_SOUTH_1","electable_nodes":3,"priority":7},
  {"region_name":"EU_SOUTH_1","electable_nodes":2,"priority":6}
]'
```

`AP_SOUTH_1` = Mumbai, `EU_SOUTH_1` = Milan. This same cluster serves every demo below — no reprovisioning between topics.

---

## Topic 1 — Automated Data Lifecycle Management

**Goal:** show that infrequently accessed records move automatically from the live cluster to cloud object storage and remain queryable through a single unified connection string.

**Run order:**
1. `cd ../mongodb-walkthrough/online-archive`
2. `python3 setup_archive.py` (in advance — Atlas archive jobs run on a daily schedule)
3. Atlas UI → **Online Archive** → walk through the rule definition, last archive run, total data archived
4. Atlas UI → **Online Archive** → **Connect** → show the federated `mongodb://` endpoint
5. `python3 query_demo.py` to contrast hot-only vs. federated query timing
6. `python3 title_lookup.py "The Matrix"` and `python3 title_lookup.py "Curious George"` to show a specific document on each tier

**Anchor points:**
- One connection string spans both tiers; the application is unchanged
- Partition fields function as the cold-tier index — the federated endpoint skips irrelevant objects rather than scanning the full archive
- Archived data is recoverable: `teardown_archive.py` rehydrates before rule deletion

---

## Topic 2 — Performance & Connection Management

**Goal:** demonstrate that the MongoDB driver manages connection pooling natively, removing the need for an external proxy tier.

**Run order:**
1. `cd ../mongodb-walkthrough/connection-pooling`
2. `python3 demo.py` — prints a timing table for new-client-per-op, pooled sequential, and pooled concurrent

**Anchor points (contrast with hardware-proxy patterns):**
- `MongoClient` is thread-safe and intended as a process-wide singleton — one instance serves every tenant database
- Default pool size is 100 connections; `maxPoolSize` is tunable per workload
- Atlas connection limits are per-tier — pool sizing on the application side directly drives consumption, no proxy hop required
- Topology changes (failover, scale events) are handled by the driver transparently — the connection string does not change

---

## Topic 3 — Multi-Tenancy & Isolation

**Goal:** show database-per-tenant isolation backed by Atlas RBAC, with a live cross-tenant access attempt that is rejected at the server.

**Run order:**
1. `cd ../mongodb-walkthrough/multi-tenancy`
2. `python3 setup_tenants.py` (idempotent — safe to re-run before the session)
3. `python3 demo.py` runs:
   - Section 1 — namespace overview (three tenant databases, same collection structure, different data)
   - Section 2 — same query against three tenants returns the title only from the tenant that owns it
   - Section 3 — tenant-scoped credential succeeds on its own database, fails with `OperationFailure` against another tenant's
   - Section 4 — one-line routing primitive: `client[db_name]` from a tenant identifier
4. Atlas UI → **Database Access** → show the three scoped database users and their per-database roles

**Anchor points:**
- Isolation is structural (namespace) and reinforced by RBAC — two independent layers
- Each tenant database can have its own indexes, schema validation rules, and collection structure
- Pattern scales to hundreds–low thousands of tenants on a single cluster; sharding extends it further

---

## Topic 4 — Regional Deployment

**Goal:** demonstrate live region topology, failover behaviour, and the network primitives that support data residency.

**Atlas UI walkthrough:**
1. Cluster overview → region map with node indicators (Mumbai primary, Milan secondaries)
2. Cluster `...` menu → **Test Failover** — Atlas forces an election; primary moves region in seconds; connection string unchanged
3. **Real-time performance** panel → which region handles writes before and after failover
4. **Network Access** → **Peering** tab → walk through what is collected from the customer side, what Atlas returns, and the CIDR-overlap failure mode (see [`../mongodb-walkthrough/vpc-peering/README.md`](../mongodb-walkthrough/vpc-peering/README.md))
5. **Network Access** → **Private Endpoint** tab → mention as the preferred alternative when CIDR overlap is a risk

**Optional script demo:** [`../mongodb-walkthrough/multi-region`](../mongodb-walkthrough/multi-region) contains `write_concern_demo.py`, `read_preference_demo.py`, and `read_concern_demo.py`. Run `read_preference_demo.py` to show `nearest` routing to a regional secondary on the multi-region cluster — useful if the audience wants to see the driver-side controls.

**Anchor points:**
- Region priority is data: change the `CLUSTER_REGIONS` array and re-apply to add/remove regions without downtime
- Peering is per-region; multi-region clusters need peering in each region the application runs in
- Connection string is stable across topology changes — the driver discovers the topology at runtime

---

## Topic 5 — Addressing Data Modeling Lift (talk-through)

No live demo for this item. The walkthrough at [`../mongodb-walkthrough/data-modeling`](../mongodb-walkthrough/data-modeling) is a useful visual aid — open the side-by-side relational/document schema during this part of the conversation.

### Framing

Re-modelling a long-lived relational schema for a document store is the single highest-perceived risk in most modernization programmes. The discussion below positions how MongoDB de-risks that work — combining tooling, methodology, and Professional Services engagement.

### Tooling

- **[MongoDB Relational Migrator](https://www.mongodb.com/products/tools/relational-migrator)** — ingests an existing relational schema (DDL + sample data), proposes a target document model interactively, and generates both DDL conversion artifacts and runnable migration jobs. Supports incremental sync via CDC so cutover does not require a freeze.
- **Schema validation (`$jsonSchema`)** — enforces field types and required fields per collection once the target model is agreed, preventing drift during and after migration.
- **Schema design patterns library** — MongoDB publishes [a catalogue of patterns](https://www.mongodb.com/developer/products/mongodb/schema-design-anti-patterns/) (bucket, outlier, extended reference, schema versioning, etc.) covering the recurring cases that come up in relational-to-document translation.

### Where Professional Services contributes

MongoDB Professional Services typically engages on a relational modernization across four phases:

| Phase | PS contribution | Outcome |
|---|---|---|
| **Discovery** | Workload inventory, access-pattern analysis, identification of the highest-value first workload | Migration order with a defensible business case |
| **Design** | Schema design workshops driven by application read/write patterns, not table structure; Relational Migrator review | Target document model signed off by application and platform teams |
| **Pilot** | Joint implementation of the first workload end-to-end — schema, migration job, application layer, validation harness | Working production-shaped slice; team confidence; reusable patterns |
| **Scale-out** | Knowledge transfer, internal centre-of-excellence enablement, MongoDB University paths for the application teams | Customer team owns subsequent migrations |

### Risk mitigation patterns we recommend

- **Migrate one workload at a time.** Modernization succeeds workload-by-workload, not as a single cutover.
- **Dual-write / dual-read during transition.** Application writes to both stores; reads are switched per workload once parity is proven. Relational Migrator's CDC mode supports this directly.
- **Validation harness in the pipeline.** Row-and-document comparison on every migration batch — surfaces type mismatches and edge cases (mixed-type fields, malformed dates, etc.) before they reach production.
- **Schema versioning from day one.** Every document carries a `schema_version` field; the application handles `v1` and `v2` concurrently during rollout.
- **Keep the document model close to access patterns.** Embed what is read together, reference what has an independent lifecycle, snapshot point-in-time values. The walkthrough document covers the decision matrix.

### What success looks like

- Application reads collapse from N joins to a single document fetch
- Schema changes ship at the application's release cadence, not the DBA team's
- The data team owns one storage technology rather than database + cache + search

---

## Reset between sessions

```bash
# Optional — only if you want a clean state for the next run
cd ../mongodb-walkthrough/multi-tenancy && python3 teardown_tenants.py
cd ../mongodb-walkthrough/online-archive && python3 teardown_archive.py
```

The cluster itself stays up. To fully tear down at the end of the engagement:

```bash
cd ../atlas-cluster-provisioning && ./teardown.sh
```
