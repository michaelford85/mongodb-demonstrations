# Multi-Region Availability

This is a conceptual walkthrough — no script is required. The cluster topology itself is the demo. Spin up a multi-region cluster using [`../../atlas-cluster-provisioning`](../../atlas-cluster-provisioning) and walk through the points below in the Atlas UI.

---

## How Atlas distributes a replica set across regions

A MongoDB Atlas cluster is always a **replica set**: typically 3 or 5 nodes, one of which holds the primary (all writes go here) and the rest are secondaries (replicate from the primary, can serve reads).

When nodes are spread across multiple regions, Atlas continues to guarantee:

- **Automatic failover** — if the primary region goes down, an election completes in seconds and a secondary in a surviving region becomes the new primary
- **No data loss** — writes are only acknowledged after being replicated to a majority of nodes
- **Read locality** — applications can be configured to read from the nearest secondary, reducing latency for read-heavy workloads

```
Region A (priority 7)     Region B (priority 6)     Region C (priority 5)
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  PRIMARY  (1)    │◄────►│  SECONDARY (2)   │      │  SECONDARY (2)   │
│  (all writes)    │      │                  │      │                  │
└──────────────────┘      └──────────────────┘      └──────────────────┘
        ▲ any region failure triggers automatic re-election
```

---

## Priority and electable nodes

Each region in the cluster configuration has a **priority** (7 = highest). The node with the highest priority that is reachable by a majority will be elected primary.

In [`../../atlas-cluster-provisioning/.env.example`](../../atlas-cluster-provisioning/.env.example), a three-region deployment looks like:

```env
CLUSTER_NUM_REGIONS=3
CLUSTER_REGIONS='[
  {"region_name":"EU_SOUTH_1","electable_nodes":3,"priority":7},
  {"region_name":"AP_SOUTH_1","electable_nodes":2,"priority":6},
  {"region_name":"US_EAST_1","electable_nodes":2,"priority":5}
]'
```

| AWS Region identifier | Location |
|---|---|
| `EU_SOUTH_1` | Milan |
| `AP_SOUTH_1` | Mumbai |
| `US_EAST_1` | N. Virginia |

> Atlas uses uppercase with underscores for region names. The values above are AWS identifiers.
> GCP and Azure follow the same pattern with their own region strings.

---

## What to show in the Atlas UI

1. **Cluster overview** → the region map with node indicators
2. **Test failover** (Atlas UI → `...` → Test Failover) — Atlas forces a primary election; the cluster is back online within seconds
3. **Real-time performance panel** → observe which region is handling writes during and after failover
4. **Network Access** → note that the cluster endpoint does not change; drivers handle the topology shift transparently

---

## Key talking points

- The application connection string never changes — the driver discovers topology changes automatically
- Atlas manages the replication lag monitoring, election timeouts, and oplog sizing
- Cross-region replication is synchronous from the write-acknowledgment perspective: a write is not confirmed until a majority of nodes (across regions) have recorded it
- Adding a read preference of `nearest` in the driver routes reads to the closest node without any application-layer logic
