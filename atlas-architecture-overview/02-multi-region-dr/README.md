# 02 — Multi-region DR

A single Atlas replica set can span continents, reads can be routed by latency, and a region outage resolves itself through an automatic election. The scripts here make each of those visible.

## What this demonstrates

| Concept | How |
|---|---|
| **Geographic distribution** | `show_topology.py` lists each member's host, state, priority, replication lag, and (when Atlas tags them) provider/region. |
| **Locality-aware reads** | `read_pref_latency.py` times the same query under `primary`, `secondaryPreferred`, and `nearest` read preferences. `nearest` wins when the client is co-located with a secondary. |
| **Region failure ≈ election** | Trigger **Test Primary Failover** in the Atlas UI; re-run `show_topology.py`; the primary has moved to a different region with no data loss. |

---

## Prerequisites

The replica-set cluster must span multiple regions. Use the template at [`.env.multi-region.example`](./.env.multi-region.example) to redeploy `atlas-cluster-provisioning` with a 3-region topology:

```bash
# in atlas-cluster-provisioning/
cp .env .env.bak
# merge the CLUSTER_NUM_REGIONS and CLUSTER_REGIONS overrides from the template
./deploy.sh
# copy the new SRV string into atlas-architecture-overview/.env (REPLICASET_URI)
```

---

## Run it

```bash
# Snapshot of the topology
python 02-multi-region-dr/show_topology.py

# Latency comparison across read preferences (~10 s)
python 02-multi-region-dr/read_pref_latency.py
```

Then in the Atlas UI:
1. Open the replica-set cluster.
2. **... → Test Primary Failover**.
3. Wait ~20 s, re-run `show_topology.py`.

Expected: the `PRIMARY` row now points at a host in a different region; `LAG (s)` is near zero on the new primary; previous primary now reads `SECONDARY`.

---

## Notes

- The provider/region columns rely on Atlas exposing member tags via `replSetGetConfig`. If they show as `?/?` it just means Atlas isn't tagging this cluster's members; the host name is still distinctive enough to read from the Atlas UI.
- `read_pref_latency.py` reads a tiny seed collection (`dr_latency_probe`); it's safe to re-run.
- Cleanup: `mongosh "$REPLICASET_URI" --eval 'use architecture_demo; db.dr_latency_probe.drop()'`
