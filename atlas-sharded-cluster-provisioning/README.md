# Atlas Sharded Cluster Provisioning (Terraform)

This folder contains a **Terraform-based script** for spinning up and tearing down an ephemeral MongoDB Atlas **sharded** cluster for educational purposes. It is a companion to [`atlas-cluster-provisioning`](../atlas-cluster-provisioning/), which provisions an unsharded replica set. Run `deploy.sh` to create the sharded cluster, run `teardown.sh` when you are done.

The shard count and the region(s) for each individual shard are driven entirely from `.env`, so you can demonstrate everything from "two shards co-located in one region" to "two shards each spanning multiple regions on different continents".

---

## What it creates

| Resource | Description |
|---|---|
| `mongodbatlas_advanced_cluster` | A **sharded** cluster (M30+) inside an existing Atlas project. `CLUSTER_TYPE=SHARDED` (default) keeps every shard in the same region(s); `CLUSTER_TYPE=GEOSHARDED` lets each shard live in a different region by assigning it its own zone. Compute Auto-Scale enabled by default. |
| `mongodbatlas_database_user` | Three users: an `atlasAdmin` admin user, a `readWriteAnyDatabase` application user, and a `clusterMonitor` monitoring user |
| `mongodbatlas_search_deployment` | Dedicated Atlas Search nodes *(only when `CLUSTER_SEARCH_NODES > 0`)* |

The configuration uses the **new sharding schema** introduced in Atlas provider 1.18 — one `replication_specs` block per shard. The deprecated `num_shards` attribute is not used, which means each shard can be placed independently.

Compute Auto-Scale is enabled with `min == max == CLUSTER_INSTANCE_SIZE` by default — the feature is on (which Atlas Automated Embedding / `autoEmbed` vector search indexes require) but the cluster does not actually scale unless you raise `CLUSTER_COMPUTE_MAX_INSTANCE_SIZE`. It is skipped entirely on local NVMe clusters, which Atlas does not auto-scale.

Storage is network-attached SSD by default; set `CLUSTER_STORAGE_CLASS=NVME` for local NVMe SSDs, or `CLUSTER_DISK_SIZE_GB` to size the SSD volume. See [Storage: SSD vs local NVMe](#storage-ssd-vs-local-nvme).

Everything is destroyed cleanly by `teardown.sh` — no manual cleanup in the Atlas UI is needed.

> **Cost note:** A sharded cluster runs at least one replica set per shard. Two M30 shards × 3 nodes each = 6 nodes minimum, so a sharded demo costs roughly 2× an equivalent single replica set demo. Tear down promptly when you are finished.

---

## Prerequisites

| Tool | Install |
|---|---|
| [Terraform](https://developer.hashicorp.com/terraform/install) ≥ 1.5 | `brew install terraform` |
| [jq](https://jqlang.github.io/jq/) | `brew install jq` |
| MongoDB Atlas account | [cloud.mongodb.com](https://cloud.mongodb.com) |
| Atlas programmatic API key | Atlas UI → Access Manager → API Keys |

The API key needs at least the **Project Owner** role on the target project.

---

## Setup

**1. Copy the environment template:**

```bash
cp .env.example .env
```

**2. Fill in `.env`.**

The key variables are:

```env
ATLAS_PUBLIC_KEY=...          # Atlas API public key
ATLAS_PRIVATE_KEY=...         # Atlas API private key

ATLAS_PROJECT_ID=...          # Atlas UI → your project → Settings → Project ID
CLUSTER_NAME=demo-sharded-cluster

CLUSTER_TYPE=SHARDED          # SHARDED (all shards share one zone) | GEOSHARDED (one zone per shard)
CLUSTER_CLOUD_PROVIDER=AWS    # AWS | GCP | AZURE — applies to every shard
CLUSTER_INSTANCE_SIZE=M30     # M30 is the minimum tier for sharded clusters; or an NVMe tier, e.g. M40_NVME
CLUSTER_STORAGE_CLASS=SSD     # SSD (network-attached) | NVME (local NVMe SSD)
CLUSTER_DISK_SIZE_GB=0        # 0 = Atlas default for the tier; SSD only
CLUSTER_BACKUP_ENABLED=false  # Atlas Cloud Backup; forced on for NVMe
MONGODB_VERSION=8.0

# Number of shards (must match the array length in CLUSTER_SHARDS)
CLUSTER_NUM_SHARDS=2

# Shard topology — JSON array. One object per shard.
# Each shard has its own region_configs list. With CLUSTER_TYPE=SHARDED
# every shard's region_configs must be identical; with CLUSTER_TYPE=GEOSHARDED
# each shard lives in its own zone and can use different regions.
#   region_name     : Atlas region string (see note below)
#   electable_nodes : nodes in this region eligible to be elected primary
#   priority        : 7 = primary (highest), 6, 5 … for secondaries
CLUSTER_SHARDS='[
  {"region_configs":[{"region_name":"US_EAST_1","electable_nodes":3,"priority":7}]},
  {"region_configs":[{"region_name":"US_EAST_1","electable_nodes":3,"priority":7}]}
]'

CLUSTER_SEARCH_NODES=0        # 0 = shared search; >0 = dedicated search nodes

# Compute Auto-Scale. Required by Atlas Automated Embedding (autoEmbed).
# Leave the max blank to pin max = CLUSTER_INSTANCE_SIZE (cheapest).
CLUSTER_COMPUTE_AUTOSCALE_ENABLED=true
CLUSTER_COMPUTE_MAX_INSTANCE_SIZE=

DB_ADMIN_USER=admin
DB_ADMIN_PASSWORD=<strong-password>

# Application user (readWriteAnyDatabase) and monitoring user (clusterMonitor)
DB_APP_USER=app-user
DB_APP_PASSWORD=<strong-password>
DB_MONITOR_USER=monitor-user
DB_MONITOR_PASSWORD=<strong-password>
```

> **Atlas region name format:** Atlas uses uppercase with underscores, e.g. `US_EAST_1`,
> `EU_WEST_1`, `EU_SOUTH_1` (Milan), `AP_SOUTH_1` (Mumbai). Find the exact string in the
> Atlas UI when you create a cluster manually, or in the
> [Atlas provider docs](https://www.mongodb.com/docs/atlas/reference/amazon-aws/#std-label-amazon-aws).

---

## Deploy

```bash
./deploy.sh
```

The script will:
1. Validate all required variables are set and that `CLUSTER_NUM_SHARDS` matches the `CLUSTER_SHARDS` array length.
2. Verify every shard declares at least one `region_configs` entry.
3. Run `terraform init` and `terraform apply`.
4. Print the cluster connection strings once provisioning is complete.

Atlas typically takes **7–15 minutes** to provision a new sharded cluster (longer than an unsharded one because each shard is a full replica set). Terraform waits for the cluster to reach the `IDLE` state before returning.

---

## Connect

After `deploy.sh` completes, grab the SRV connection string from the Terraform output:

```
connection_strings = {
  standard_srv = "mongodb+srv://<cluster-host>/?retryWrites=true&w=majority"
}
```

Use `DB_ADMIN_USER` / `DB_ADMIN_PASSWORD` from your `.env` to authenticate. `DB_APP_USER` (read/write on all databases) and `DB_MONITOR_USER` (diagnostics only) are also created for least-privilege access. The SRV string points at the cluster's `mongos` routers — your driver will automatically route reads and writes to the appropriate shard based on the shard key of each collection. (Collections are unsharded by default; use `sh.shardCollection()` from the shell to enable sharding on a specific collection.)

---

## Teardown

```bash
./teardown.sh
```

You will be prompted to type the cluster name to confirm. All resources (cluster, database users, and any dedicated search nodes) are destroyed.

---

## Storage: SSD vs local NVMe

`CLUSTER_STORAGE_CLASS` selects the storage backing every shard.

| | `SSD` (default) | `NVME` |
|---|---|---|
| Backing store | Network-attached SSD | Local NVMe SSD attached to the host |
| Tier name sent to Atlas | `CLUSTER_INSTANCE_SIZE` (e.g. `M40`) | `CLUSTER_INSTANCE_SIZE` + `_NVME` (e.g. `M40_NVME`) |
| `CLUSTER_DISK_SIZE_GB` | Configurable (`0` = Atlas default, otherwise 10–4096) | Must be `0` — capacity is fixed per tier |
| Availability | AWS, GCP, Azure | AWS from M40, Azure from M60. Not offered on GCP |
| Compute / disk auto-scale | Available (enabled by default) | Not supported — the auto-scale block is skipped |
| Cloud Backup | Optional (`CLUSTER_BACKUP_ENABLED`, off by default) | Mandatory — forced on |

Setting `CLUSTER_INSTANCE_SIZE=M40_NVME` directly is equivalent to `CLUSTER_INSTANCE_SIZE=M40` plus `CLUSTER_STORAGE_CLASS=NVME`; Terraform normalises the two inputs into a single tier name. Atlas requires the disk size to be equal across all shards and node types, so the value applies uniformly.

Because Atlas does not auto-scale local NVMe clusters, an NVMe cluster cannot satisfy the Compute Auto-Scale prerequisite for Atlas Automated Embedding (`autoEmbed` vector search indexes). Use `SSD` for those demos.

---

## SHARDED vs GEOSHARDED

Atlas exposes two cluster types relevant here:

| Type | Zones | Per-shard regions | When to use |
|---|---|---|---|
| `SHARDED` | All shards share one zone | Every shard **must** have the same `region_configs` | Multiple shards in the same region(s) — horizontal scale, simpler topology, cheapest |
| `GEOSHARDED` | Each shard gets its own zone (`Zone 1`, `Zone 2`, …) | Each shard can use different regions | Shards distributed across geographies (e.g. shard 1 in EU, shard 2 in US) |

Atlas enforces the SHARDED uniformity rule on the server side — if your `CLUSTER_SHARDS` array contains shards with different `region_configs` while `CLUSTER_TYPE=SHARDED`, the API rejects the request with `ASYMMETRIC_REGION_TOPOLOGY_IN_ZONE`. `deploy.sh` catches this before calling Atlas and prints a clearer message.

This Terraform takes care of zone assignment automatically: when `CLUSTER_TYPE=GEOSHARDED`, each `replication_specs` block is given `zone_name = "Zone N"` based on its position in the shard list. You don't need to specify zones manually.

---

## Examples

### Two shards co-located in one region (SHARDED)

The simplest sharded demo — both shards in US East, sharing one zone:

```env
CLUSTER_TYPE=SHARDED
CLUSTER_CLOUD_PROVIDER=AWS
CLUSTER_NUM_SHARDS=2
CLUSTER_SHARDS='[
  {"region_configs":[{"region_name":"US_EAST_1","electable_nodes":3,"priority":7}]},
  {"region_configs":[{"region_name":"US_EAST_1","electable_nodes":3,"priority":7}]}
]'
```

### Two shards geo-distributed across continents (GEOSHARDED)

Shard 1 lives in Europe, shard 2 lives in North America:

```env
CLUSTER_TYPE=GEOSHARDED
CLUSTER_CLOUD_PROVIDER=AWS
CLUSTER_NUM_SHARDS=2
CLUSTER_SHARDS='[
  {"region_configs":[{"region_name":"EU_WEST_1","electable_nodes":3,"priority":7}]},
  {"region_configs":[{"region_name":"US_EAST_1","electable_nodes":3,"priority":7}]}
]'
```

### Two shards, each spanning multiple regions (GEOSHARDED)

Each shard is itself a multi-region replica set. Shard 1 has its primary in Ireland with a secondary in Milan; shard 2 has its primary in US East with a secondary in Mumbai:

```env
CLUSTER_TYPE=GEOSHARDED
CLUSTER_CLOUD_PROVIDER=AWS
CLUSTER_NUM_SHARDS=2
CLUSTER_SHARDS='[
  {"region_configs":[
    {"region_name":"EU_WEST_1","electable_nodes":2,"priority":7},
    {"region_name":"EU_SOUTH_1","electable_nodes":1,"priority":6}
  ]},
  {"region_configs":[
    {"region_name":"US_EAST_1","electable_nodes":2,"priority":7},
    {"region_name":"AP_SOUTH_1","electable_nodes":1,"priority":6}
  ]}
]'
```

### Three shards in a single region (SHARDED)

The simplest way to add more horizontal capacity — three identical shards co-located in US East:

```env
CLUSTER_TYPE=SHARDED
CLUSTER_NUM_SHARDS=3
CLUSTER_SHARDS='[
  {"region_configs":[{"region_name":"US_EAST_1","electable_nodes":3,"priority":7}]},
  {"region_configs":[{"region_name":"US_EAST_1","electable_nodes":3,"priority":7}]},
  {"region_configs":[{"region_name":"US_EAST_1","electable_nodes":3,"priority":7}]}
]'
```

> **Notes**
> - Sharded clusters require **M30 or larger**.
> - Each shard's `electable_nodes` total should be odd (3 or 5) and include exactly one `priority: 7` region.
> - Multi-region shards take longer to provision and cost more — every region adds nodes.

---

## Files

| File | Purpose |
|---|---|
| `main.tf` | Provider, sharded cluster, search nodes, and database user resources |
| `variables.tf` | All input variable declarations |
| `outputs.tf` | Connection strings, cluster ID, and state emitted after apply |
| `deploy.sh` | Validates `.env`, exports `TF_VAR_*`, runs `terraform apply` |
| `teardown.sh` | Confirms intent, exports `TF_VAR_*`, runs `terraform destroy` |
| `.env.example` | Template for all required environment variables |
| `.gitignore` | Excludes `.env`, Terraform state, and the `.terraform/` cache |

---

## Troubleshooting

**`Error: 403 Forbidden` from Atlas API**
Your API key does not have the Project Owner role on the target project. Check Access Manager in the Atlas UI.

**`CLUSTER_NUM_SHARDS=N but CLUSTER_SHARDS contains M entries`**
The `CLUSTER_NUM_SHARDS` value must equal the number of objects in the `CLUSTER_SHARDS` JSON array.

**`Every shard in CLUSTER_SHARDS must include a non-empty region_configs array`**
Each shard object must contain a `region_configs` key whose value is a non-empty JSON array.

**`Error: Invalid JSON for cluster_shards`**
The `CLUSTER_SHARDS` value in `.env` must be valid JSON. Validate it with:
```bash
echo "$CLUSTER_SHARDS" | jq .
```

**`Error: SHARDED clusters require minimum instance size M30`**
Sharding is not supported on M10 or M20 tiers. Set `CLUSTER_INSTANCE_SIZE=M30` (or larger) in `.env`.

**`HTTP 400 Bad Request (Error code: "ASYMMETRIC_REGION_TOPOLOGY_IN_ZONE")`**
You are running with `CLUSTER_TYPE=SHARDED` (the default) but your `CLUSTER_SHARDS` entries do not all share the same `region_configs`. Atlas requires every shard in a single zone to have an identical region topology. Either align the `region_configs` across all shards, or set `CLUSTER_TYPE=GEOSHARDED` to place each shard in its own zone. (`deploy.sh` now catches this mismatch before calling the API; if you hit it from the API directly, update `.env` accordingly.)

**`ERROR: local NVMe storage is only offered on AWS and AZURE`**
Local NVMe is not available on GCP. Either set `CLUSTER_STORAGE_CLASS=SSD` or switch `CLUSTER_CLOUD_PROVIDER` to `AWS`/`AZURE`.

**`CANNOT_MODIFY_DISK_SIZE_FOR_NVME_CLUSTER` / `cluster_disk_size_gb must be 0 with local NVMe storage`**
NVMe tiers have a fixed disk capacity. Set `CLUSTER_DISK_SIZE_GB=0` and pick a larger NVMe tier if you need more space.

**`Cannot create an NVMe cluster without Cloud Backup enabled` (`ATLAS_GENERAL_ERROR`)**
Atlas requires Cloud Backup on local NVMe clusters. `deploy.sh` now forces `CLUSTER_BACKUP_ENABLED=true` whenever NVMe is selected, so re-run `./deploy.sh`. Note that backup snapshots add cost, and a sharded cluster snapshots every shard.

**`HTTP 400 … INVALID_INSTANCE_SIZE` with an `_NVME` tier**
The requested tier is not offered as NVMe in that region. NVMe starts at M40 on AWS and M60 on Azure, and not every region carries every NVMe tier — check the tier list in the Atlas UI for your region.

**`HTTP 400 … NO_COMMON_INSTANCE_FAMILY`**
"There is no common supported instance family in the selected regions." The tier itself is available in every region in your `region_configs`, but the underlying host families differ, and Atlas needs one family that covers them all. This is easy to hit with `CLUSTER_STORAGE_CLASS=NVME` across regions, because each NVMe tier maps to a specific host family. Either reduce each shard to a single region, or try a different secondary region until the tier resolves to a shared family. `CLUSTER_STORAGE_CLASS=SSD` is not affected.

**Cluster stuck provisioning**
Sharded clusters take longer than replica sets because Atlas provisions every shard plus the config server replica set and `mongos` routers. Check the Atlas UI → Clusters page for status; Terraform will keep waiting until the cluster reaches `IDLE`.

**`Automated Embedding on cluster '<name>' requires Compute Auto-Scale enabled`**
The cluster was provisioned (or modified) with `CLUSTER_COMPUTE_AUTOSCALE_ENABLED=false`. Set `CLUSTER_COMPUTE_AUTOSCALE_ENABLED=true` in `.env` and re-run `./deploy.sh` — Atlas will enable Compute Auto-Scale in place.
