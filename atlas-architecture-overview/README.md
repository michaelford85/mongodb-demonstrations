# Atlas Architecture Overview

A hands-on tour of three MongoDB Atlas architecture topics — durability, geographic distribution, and sharding — using the two clusters provisioned by the sibling Terraform folders as a visual aide.

| Topic | Cluster | Format |
|---|---|---|
| [01 — RPO / RTO](./01-rpo-rto/) | Replica set | Python |
| [02 — Multi-region DR](./02-multi-region-dr/) | Replica set (multi-region) | Python |
| [03 — Sharding options](./03-sharding/) | GEOSHARDED cluster | mongosh `.js` + Python helpers |

The Atlas UI covers the *configuration* side — Continuous Backup settings, Test Failover button, Global Writes tab. The scripts in this folder cover the *runtime* side — what failover looks like as it happens, where data physically lives, and how the balancer redistributes chunks under different shard keys.

---

## Prerequisites

| Tool | Install |
|---|---|
| Python 3.10+ | `brew install python` |
| [mongosh](https://www.mongodb.com/docs/mongodb-shell/install/) | `brew install mongosh` |
| Two Atlas clusters | provisioned via `../atlas-cluster-provisioning` and `../atlas-sharded-cluster-provisioning` |

```bash
cd atlas-architecture-overview
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — paste both SRV connection strings
```

> The shared `.env` is the single source of truth for credentials. Every subfolder's scripts load it from the root.

---

## Walkthrough (≈ 30 min end-to-end)

### Topic 1 — RPO / RTO (≈ 8 min)

1. Open the Atlas UI on the replica-set cluster. **Backup → Continuous Cloud Backup** — the PIT slider and retention policy illustrate RPO measured in seconds.
2. Run `01-rpo-rto/writer.py` and `01-rpo-rto/watcher.py` side-by-side.
3. In the Atlas UI: **... → Test Primary Failover**.
4. The watcher swaps primaries and the writer pauses then resumes — RTO measured in tens of seconds, with no data loss.

### Topic 2 — Multi-region DR (≈ 8 min)

1. Re-deploy `atlas-cluster-provisioning` with a 3-region `CLUSTER_REGIONS` (template in `02-multi-region-dr/.env.multi-region.example`), or point at an existing multi-region cluster.
2. Run `02-multi-region-dr/show_topology.py` — shows each member's host, state, lag, and priority.
3. Run `02-multi-region-dr/read_pref_latency.py` — `nearest` and `secondaryPreferred` read from the closest member; `primary` may cross an ocean.
4. Trigger **Test Primary Failover** again, re-run `show_topology.py`, and the primary has moved to a different region.

### Topic 3 — Sharding options (≈ 14 min)

1. Connect mongosh to the sharded cluster:
   ```bash
   mongosh "$SHARDED_URI"
   ```
2. Run `03-sharding/seed.py` once to load ~100 k documents into `architecture_demo.events`.
3. Start `03-sharding/chunk_map.py` in a side terminal — refreshes chunk counts per shard every 2 s.
4. In mongosh, work through the three `.js` files in order:
   - `01_hashed.js`  — hashed shard key, even distribution
   - `02_ranged.js`  — monotonically-increasing key, classic anti-pattern (one shard hot)
   - `03_zoned.js`  — compound key with location prefix; zone ranges route EU traffic to Zone 1 and US traffic to Zone 2 (uses the GEOSHARDED cluster's existing zones)

---

## Files

| Path | Purpose |
|---|---|
| `.env.example` | Template for both cluster connection strings |
| `requirements.txt` | Python dependencies (PyMongo, python-dotenv) |
| `01-rpo-rto/` | Failover behaviour demo |
| `02-multi-region-dr/` | Geographic distribution demo |
| `03-sharding/` | Sharding strategy demo |

---

## Notes

- Every Python script connects via `pymongo` with `retryWrites=true` and `w="majority"` so failover is non-destructive. Re-running any script is safe.
- Topic 3 mongosh scripts use `sh.updateZoneKeyRange` directly — they do **not** configure Atlas Global Writes through the Atlas API, so the Atlas UI may still show "no collections configured for Global Writes". The routing works regardless.
- Tear down the demo database afterward with `mongosh "$REPLICASET_URI" --eval 'use architecture_demo; db.dropDatabase()'` (and the same on `$SHARDED_URI`).
