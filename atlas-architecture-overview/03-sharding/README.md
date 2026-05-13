# 03 — Sharding strategies

Three sharding strategies applied to the same dataset, plus a look at how the GEOSHARDED cluster's two zones enable location-aware routing.

## What this demonstrates

| Strategy | Shard key | Behaviour |
|---|---|---|
| **Hashed** (`01_hashed.js`) | `{ customer_id: "hashed" }` | Uniform distribution across shards. Excellent for write throughput; bad for range scans. |
| **Ranged** (`02_ranged.js`) | `{ created_at: 1 }` | Monotonic key → all new inserts hit one shard. The classic anti-pattern; included to show *why* hashed is usually correct. |
| **Zoned** (`03_zoned.js`) | `{ location: 1, customer_id: 1 }` + zone ranges | EU docs land on Zone 1 (EU shard); US docs land on Zone 2 (US shard). Location-aware routing with no app changes. |

---

## Prerequisites

- The GEOSHARDED cluster from `../atlas-sharded-cluster-provisioning` is up and `SHARDED_URI` is set in the shared root `.env`.
- `mongosh` is installed and on `PATH`.
- The DB user has the `atlasAdmin` role (granted by the Terraform).

---

## Run it

### One-off — seed the data

```bash
python 03-sharding/seed.py
```
Drops and repopulates `architecture_demo.events` with 100 k synthetic documents (`customer_id`, `created_at`, `location`, `amount`).

### Live monitor — keep this running in a side terminal

```bash
python 03-sharding/chunk_map.py
```
Refreshes per-shard doc counts every 2 s using `collStats`. You'll watch the bars shift as each strategy is applied.

### Strategy walkthrough — in mongosh

```bash
mongosh "$SHARDED_URI"
```

Then load each script in order:

```javascript
load("03-sharding/01_hashed.js")     // even distribution
// re-seed if you want fresh inserts: python 03-sharding/seed.py
load("03-sharding/02_ranged.js")     // hotspot
load("03-sharding/03_zoned.js")      // EU → Zone 1, US → Zone 2
```

Each `.js` drops the collection if it was previously sharded with a different key (you can't change a shard key in place without `reshardCollection`, which is out of scope for this demo). Re-run `seed.py` between scripts to get a fresh data set to watch redistribute.

After `03_zoned.js`, prove out routing in mongosh:

```javascript
use architecture_demo
db.events.find({ location: "EU" }).explain()
    .queryPlanner.winningPlan.shards
// → only the EU shard appears
```

---

## Notes

- The zone names (`Zone 1`, `Zone 2`) match the names assigned by the Terraform in `../atlas-sharded-cluster-provisioning/main.tf` when `cluster_type = "GEOSHARDED"`. If you renamed zones, update `03_zoned.js`.
- This demo configures sharding zones at the mongosh level (`sh.updateZoneKeyRange`). It does **not** call the Atlas Admin API for Global Writes, so the Atlas UI's *Global Writes* tab may still display "no collections configured". The routing works regardless — verify with `.explain()`.
- Cleanup: `mongosh "$SHARDED_URI" --eval 'use architecture_demo; db.dropDatabase()'`
