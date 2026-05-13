# Multi-Region Availability

Spin up a multi-region cluster with [`../../atlas-cluster-provisioning`](../../atlas-cluster-provisioning), then use the scripts here to demonstrate how write concern, read concern, and read preference let you tune the consistency, durability, and latency of every operation.

---

## Setup

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
# Fill in MONGODB_URI
```

---

## How Atlas distributes a replica set across regions

A MongoDB Atlas cluster is always a **replica set**: typically 3 or 5 nodes, one of which is the primary (all writes land here) and the rest are secondaries (replicate from the primary, can serve reads).

When nodes span multiple regions, Atlas guarantees:

- **Automatic failover** — if the primary region goes down, an election completes in seconds and a secondary in a surviving region becomes the new primary
- **No data loss** — writes are only acknowledged after being replicated to a majority of nodes
- **Read locality** — applications can be configured to read from the nearest secondary, reducing latency for read-heavy workloads

```
Region A (priority 7)     Region B (priority 6)     Region C (priority 5)
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  PRIMARY  (1)    │◄────►│  SECONDARY (2)   │      │  SECONDARY (2)   │
│  (all writes)    │      │                  │      │                  │
└──────────────────┘      └──────────────────┘      └──────────────────┘
        ↑ any region failure triggers automatic election
```

Priority and region topology are set in [`../../atlas-cluster-provisioning/.env.example`](../../atlas-cluster-provisioning/.env.example):

```env
CLUSTER_NUM_REGIONS=3
CLUSTER_REGIONS='[
  {"region_name":"EU_SOUTH_1","electable_nodes":3,"priority":7},
  {"region_name":"AP_SOUTH_1","electable_nodes":2,"priority":6},
  {"region_name":"US_EAST_1","electable_nodes":2,"priority":5}
]'
```

---

## Write Concern

Write concern controls **when MongoDB considers a write complete** — specifically, how many nodes must acknowledge a write before the driver returns.

| Level | Meaning | Trade-off |
|---|---|---|
| `w=0` | Unacknowledged — fire and forget | Fastest; no confirmation, silent failures |
| `w=1` | Primary acknowledges (default) | Fast; secondaries may not have it yet |
| `w=2` | Primary + at least one secondary | Survives one node loss |
| `w="majority"` | A majority of nodes confirm | Survives region failure; higher latency |
| `w="majority"` + `j=True` | Majority + journal flush | Strongest durability; on-disk guarantee |

In a multi-region cluster the latency gap between `w=1` and `w="majority"` is measurable — `w="majority"` typically requires at least one cross-region acknowledgment.

**Run the demo:**

```bash
python3 write_concern_demo.py
```

The script writes a test document at each concern level, prints whether it was acknowledged and how long it took, then shows a summary table. Test documents are cleaned up at the end.

---

## Read Preference

Read preference controls **which node in the replica set handles a read**. The driver selects from eligible nodes based on the mode and — for `nearest` — real-time latency measurements.

| Mode | Routes to | Best for |
|---|---|---|
| `primary` | Always the primary (default) | Reads that must reflect the latest write |
| `primaryPreferred` | Primary when available, secondary otherwise | Most workloads; resilient to primary failure |
| `secondary` | Always a secondary | Offloading read load from the primary |
| `secondaryPreferred` | Secondary when available, primary otherwise | Read-heavy workloads |
| `nearest` | The node with the lowest measured latency | Geo-distributed apps; minimise read RTT |

**Run the demo:**

```bash
python3 read_preference_demo.py
```

Each mode runs the same query five times. After each query, `cursor.address` is checked against `client.primary` to confirm whether the read was served by the primary or a secondary — and which server specifically. On a multi-region cluster, `nearest` will often route to a regional secondary rather than the primary.

---

## Read Concern

Read concern controls **which version of data a query can return** — specifically, whether the returned data has been replicated to a majority of nodes.

| Level | Returns | Trade-off |
|---|---|---|
| `available` | Local node state, no replication check | Fastest; may return rolled-back data (rare on replica sets) |
| `local` | Local node state (default) | Fast; no replication guarantee |
| `majority` | Data acknowledged by a majority | Safe across failovers; slightly higher latency |
| `linearizable` | All prior majority-committed writes visible | Strongest consistency; primary only; highest latency |

**Why it matters in multi-region:**

With `w=1` a write is confirmed by the primary before secondaries have it. A subsequent `secondary` read with `local` concern might return stale data. Combining `w="majority"` writes with `majority` reads gives a consistent view regardless of which node answers.

```
Write with w="majority"  →  safe to read with read_concern="majority" from any node
Write with w=1           →  a secondary read with "local" concern may lag behind
```

**Run the demo:**

```bash
python3 read_concern_demo.py
```

The script writes a known document with `w="majority"`, then reads it back at each concern level from the primary, printing timing for each. It also verifies that `linearizable` is rejected when directed at a secondary — the server raises a `NotPrimaryError` (distinct from `OperationFailure`; it inherits from `ConnectionFailure`), confirming the constraint is enforced at the server level. Handle this in application code accordingly.

---

## Putting it together

The three settings compose. A common production configuration for a multi-region write-heavy workload:

```python
from pymongo import MongoClient, ReadPreference
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

client = MongoClient(uri)
collection = (
    client["mydb"]["mycollection"]
    .with_options(
        write_concern=WriteConcern(w="majority"),  # durable across regions
        read_preference=ReadPreference.NEAREST,    # serve reads from closest node
        read_concern=ReadConcern("majority"),       # only read committed data
    )
)
```

For a reporting workload where some staleness is acceptable:

```python
collection = (
    client["mydb"]["mycollection"]
    .with_options(
        read_preference=ReadPreference.SECONDARY_PREFERRED,
        read_concern=ReadConcern("local"),
    )
)
```

---

## Atlas UI walkthrough

1. **Cluster overview** → the region map with node indicators
2. **Test Failover** (cluster `...` menu) — Atlas forces an election; back online in seconds
3. **Real-time performance panel** → observe which region handles writes before and after failover
4. **Network Access** → the connection string never changes; the driver handles topology shifts transparently
