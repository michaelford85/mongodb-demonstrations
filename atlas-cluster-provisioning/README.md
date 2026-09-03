# Atlas Cluster Provisioning (Terraform)

This folder contains a **Terraform-based script** for spinning up and tearing down an ephemeral MongoDB Atlas project and cluster. It is the foundation for the Atlas walkthrough demos in this repository — run `deploy.sh` before any demo, run `teardown.sh` when you are done.

---

## What it creates

| Resource | Description |
|---|---|
| `mongodbatlas_advanced_cluster` | A dedicated replica set cluster (M10+) inside an existing Atlas project, with Compute Auto-Scale enabled by default |
| `mongodbatlas_database_user` | Three users: an `atlasAdmin` admin user, a `readWriteAnyDatabase` application user, and a `clusterMonitor` monitoring user |
| `mongodbatlas_search_deployment` | Dedicated Atlas Search nodes *(only when `CLUSTER_SEARCH_NODES > 0`)* |

Compute Auto-Scale is enabled with `min == max == CLUSTER_INSTANCE_SIZE` by default — the feature is on (which Atlas Automated Embedding / `autoEmbed` vector search indexes require) but the cluster does not actually scale unless you raise `CLUSTER_COMPUTE_MAX_INSTANCE_SIZE`. It is skipped entirely on local NVMe clusters, which Atlas does not auto-scale.

Storage is network-attached SSD by default; set `CLUSTER_STORAGE_CLASS=NVME` for local NVMe SSDs, or `CLUSTER_DISK_SIZE_GB` to size the SSD volume. See [Storage: SSD vs local NVMe](#storage-ssd-vs-local-nvme).

Everything is destroyed cleanly by `teardown.sh` — no manual cleanup in the Atlas UI is needed.

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
CLUSTER_NAME=demo-cluster

CLUSTER_CLOUD_PROVIDER=AWS    # AWS | GCP | AZURE
CLUSTER_INSTANCE_SIZE=M30     # or an explicit NVMe tier, e.g. M40_NVME
CLUSTER_STORAGE_CLASS=SSD     # SSD (network-attached) | NVME (local NVMe SSD)
CLUSTER_DISK_SIZE_GB=0        # 0 = Atlas default for the tier; SSD only
CLUSTER_BACKUP_ENABLED=false  # Atlas Cloud Backup; forced on for NVMe
MONGODB_VERSION=8.0

# Number of regions (must match the array length in CLUSTER_REGIONS)
CLUSTER_NUM_REGIONS=1

# Region topology — JSON array. One object per region.
# region_name     : Atlas region string (see note below)
# electable_nodes : nodes in this region eligible to be elected primary
# priority        : 7 = primary (highest), 6, 5 … for secondaries
CLUSTER_REGIONS='[{"region_name":"US_EAST_1","electable_nodes":3,"priority":7}]'

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
1. Validate all required variables are set and that `CLUSTER_NUM_REGIONS` matches the `CLUSTER_REGIONS` array length.
2. Run `terraform init` and `terraform apply`.
3. Print the cluster connection strings once provisioning is complete.

Atlas typically takes **5–10 minutes** to provision a new cluster. Terraform waits for the cluster to reach the `IDLE` state before returning.

---

## Connect

After `deploy.sh` completes, grab the SRV connection string from the Terraform output:

```
connection_strings = {
  standard_srv = "mongodb+srv://<cluster-host>/?retryWrites=true&w=majority"
}
```

Use `DB_ADMIN_USER` / `DB_ADMIN_PASSWORD` from your `.env` to authenticate. `DB_APP_USER`
(read/write on all databases) and `DB_MONITOR_USER` (diagnostics only) are also created for
least-privilege access.

---

## Teardown

```bash
./teardown.sh
```

You will be prompted to type the cluster name to confirm. All resources (cluster, project, database users) are destroyed.

---

## Storage: SSD vs local NVMe

`CLUSTER_STORAGE_CLASS` selects the storage backing the cluster.

| | `SSD` (default) | `NVME` |
|---|---|---|
| Backing store | Network-attached SSD | Local NVMe SSD attached to the host |
| Tier name sent to Atlas | `CLUSTER_INSTANCE_SIZE` (e.g. `M40`) | `CLUSTER_INSTANCE_SIZE` + `_NVME` (e.g. `M40_NVME`) |
| `CLUSTER_DISK_SIZE_GB` | Configurable (`0` = Atlas default, otherwise 10–4096) | Must be `0` — capacity is fixed per tier |
| Availability | AWS, GCP, Azure | AWS from M40, Azure from M60. Not offered on GCP |
| Compute / disk auto-scale | Available (enabled by default) | Not supported — the auto-scale block is skipped |
| Cloud Backup | Optional (`CLUSTER_BACKUP_ENABLED`, off by default) | Mandatory — forced on |

Setting `CLUSTER_INSTANCE_SIZE=M40_NVME` directly is equivalent to `CLUSTER_INSTANCE_SIZE=M40` plus `CLUSTER_STORAGE_CLASS=NVME`; Terraform normalises the two inputs into a single tier name.

Because Atlas does not auto-scale local NVMe clusters, an NVMe cluster cannot satisfy the Compute Auto-Scale prerequisite for Atlas Automated Embedding (`autoEmbed` vector search indexes). Use `SSD` for those demos.

To grow the disk on an SSD cluster, raise `CLUSTER_DISK_SIZE_GB` and re-run `./deploy.sh`.

---

## Multi-Region Example

To demonstrate geographic distribution — for example replicating across **Milan**, **Mumbai**, and **US East** with 7 total nodes:

```env
CLUSTER_CLOUD_PROVIDER=AWS
CLUSTER_NUM_REGIONS=3
CLUSTER_REGIONS='[
  {"region_name":"EU_SOUTH_1","electable_nodes":3,"priority":7},
  {"region_name":"AP_SOUTH_1","electable_nodes":2,"priority":6},
  {"region_name":"US_EAST_1","electable_nodes":2,"priority":5}
]'
```

> **Note:** Multi-region clusters cost more and take longer to provision. They also require
> each region to be available in your Atlas tier — M10+ supports multi-region on AWS.

---

## Files

| File | Purpose |
|---|---|
| `main.tf` | Provider, project, cluster, search nodes, and database user resources |
| `variables.tf` | All input variable declarations |
| `outputs.tf` | Connection strings, cluster ID, and state emitted after apply |
| `deploy.sh` | Validates `.env`, exports `TF_VAR_*`, runs `terraform apply` |
| `teardown.sh` | Confirms intent, exports `TF_VAR_*`, runs `terraform destroy` |
| `.env.example` | Template for all required environment variables |
| `.gitignore` | Excludes `.env`, Terraform state, and the `.terraform/` cache |

---

## Troubleshooting

**`Error: 403 Forbidden` from Atlas API**  
Your API key does not have the Organization Project Creator role. Check Access Manager in the Atlas UI.

**`CLUSTER_NUM_REGIONS does not match CLUSTER_REGIONS`**  
The `CLUSTER_NUM_REGIONS` value must equal the number of objects in the `CLUSTER_REGIONS` JSON array.

**`Error: Invalid JSON for cluster_regions`**  
The `CLUSTER_REGIONS` value in `.env` must be valid JSON. Validate it with:
```bash
echo "$CLUSTER_REGIONS" | jq .
```

**`ERROR: local NVMe storage is only offered on AWS and AZURE`**
Local NVMe is not available on GCP. Either set `CLUSTER_STORAGE_CLASS=SSD` or switch `CLUSTER_CLOUD_PROVIDER` to `AWS`/`AZURE`.

**`CANNOT_MODIFY_DISK_SIZE_FOR_NVME_CLUSTER` / `cluster_disk_size_gb must be 0 with local NVMe storage`**
NVMe tiers have a fixed disk capacity. Set `CLUSTER_DISK_SIZE_GB=0` and pick a larger NVMe tier if you need more space.

**`Cannot create an NVMe cluster without Cloud Backup enabled` (`ATLAS_GENERAL_ERROR`)**
Atlas requires Cloud Backup on local NVMe clusters. `deploy.sh` now forces `CLUSTER_BACKUP_ENABLED=true` whenever NVMe is selected, so re-run `./deploy.sh`. Note that backup snapshots add cost.

**`HTTP 400 … INVALID_INSTANCE_SIZE` with an `_NVME` tier**
The requested tier is not offered as NVMe in that region. NVMe starts at M40 on AWS and M60 on Azure, and not every region carries every NVMe tier — check the tier list in the Atlas UI for your region.

**`HTTP 400 … NO_COMMON_INSTANCE_FAMILY`**
"There is no common supported instance family in the selected regions." The tier itself is available in every region in `CLUSTER_REGIONS`, but the underlying host families differ, and Atlas needs one family that covers them all. This is easy to hit with `CLUSTER_STORAGE_CLASS=NVME` across regions, because each NVMe tier maps to a specific host family. Either drop to a single region, or try a different secondary region until the tier resolves to a shared family. `CLUSTER_STORAGE_CLASS=SSD` is not affected.

**Cluster stuck provisioning**
Atlas clusters can occasionally take longer than expected. Check the Atlas UI → Clusters page for status. Terraform will keep waiting.

**`Automated Embedding on cluster '<name>' requires Compute Auto-Scale enabled`**
The cluster was provisioned (or modified) with `CLUSTER_COMPUTE_AUTOSCALE_ENABLED=false`, or pre-dates this Terraform's auto-scale support. Set `CLUSTER_COMPUTE_AUTOSCALE_ENABLED=true` in `.env` and re-run `./deploy.sh` — Atlas will enable Compute Auto-Scale in place on the existing cluster.
