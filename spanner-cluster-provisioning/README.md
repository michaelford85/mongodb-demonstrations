# Spanner Cluster Provisioning (Terraform)

This folder contains a **Terraform-based script** for spinning up and tearing down an ephemeral regional Google Cloud Spanner instance and database. It is the foundation for the Spanner walkthrough demos in this repository — run `deploy.sh` before any demo, run `teardown.sh` when you are done.

---

## What it creates

| Resource | Description |
|---|---|
| `google_spanner_instance` | A regional Spanner instance sized in processing units (PU) |
| `google_spanner_database` | A database on that instance, using the dialect chosen in `.env` (Google Standard SQL or PostgreSQL) |
| `google_service_account` | A dedicated harness service account scoped to this deployment |
| `google_spanner_instance_iam_member` | Grants the harness SA `roles/spanner.databaseUser` on the instance |
| `google_service_account_key` | A JSON key for the harness SA, materialised to `harness-sa-key.json` by `deploy.sh` |

The instance is provisioned with the regional config `regional-${GCP_REGION}`. Multi-region configs (e.g. `nam3`, `eur3`, `nam-eur-asia1`) are not used by default — see the "Multi-Region Example" section below.

Everything is destroyed cleanly by `teardown.sh` — no manual cleanup in the GCP Console is needed.

---

## Prerequisites

| Tool | Install |
|---|---|
| [Terraform](https://developer.hashicorp.com/terraform/install) ≥ 1.5 | `brew install terraform` |
| [jq](https://jqlang.github.io/jq/) | `brew install jq` |
| [gcloud CLI](https://cloud.google.com/sdk/docs/install) (optional, for inspecting state) | `brew install --cask google-cloud-sdk` |
| GCP project with billing enabled | [console.cloud.google.com](https://console.cloud.google.com) |
| Provisioner service-account key (JSON) | GCP IAM → Service Accounts → Create key |

The provisioner service account needs at minimum:
- `roles/spanner.admin`
- `roles/iam.serviceAccountAdmin`
- `roles/iam.serviceAccountKeyAdmin`
- `roles/resourcemanager.projectIamAdmin` (to grant the harness SA the Spanner role)

The Spanner API (`spanner.googleapis.com`) and IAM API (`iam.googleapis.com`) must be enabled on the project.

---

## Setup

**1. Copy the environment template:**

```bash
cp .env.example .env
```

**2. Fill in `.env`.**

The key variables are:

```env
GOOGLE_APPLICATION_CREDENTIALS=/abs/path/to/provisioner-sa-key.json

GCP_PROJECT_ID=<your-gcp-project-id>
GCP_REGION=us-central1

SPANNER_INSTANCE_ID=demo-instance
SPANNER_DATABASE_ID=demo-db
SPANNER_PROCESSING_UNITS=100
SPANNER_DIALECT=GOOGLE_STANDARD_SQL
```

> **Spanner sizing:** `SPANNER_PROCESSING_UNITS` must be a multiple of 100 below 1000,
> and a multiple of 1000 above that (1000 PU = 1 node). 100 PU is the cheapest billable
> configuration.

> **Spanner region format:** GCP regions are lowercase with hyphens, e.g. `us-central1`,
> `us-east1`, `europe-west1`, `asia-southeast1`. The Spanner instance config is derived
> as `regional-${GCP_REGION}` — for multi-region see the section further down.

---

## Deploy

```bash
./deploy.sh
```

The script will:
1. Validate all required variables are set and that `GOOGLE_APPLICATION_CREDENTIALS` points to a real file.
2. Run `terraform init` and `terraform apply` against the `terraform/` subfolder.
3. Materialise the harness service-account key to `harness-sa-key.json` (mode 0600) for the demo harness to consume.

Spanner instance provisioning typically completes in **under a minute** for a regional configuration.

---

## Connect

After `deploy.sh` completes, point your harness at the database using the outputs:

```
database_path                 = "projects/<project>/instances/<instance>/databases/<db>"
harness_service_account_email = "sp-<instance>-sa@<project>.iam.gserviceaccount.com"
```

Authenticate the harness using the key file written by `deploy.sh`:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/harness-sa-key.json"
```

Client libraries (`google-cloud-spanner`) will pick up the credentials and route to the database at `database_path`.

---

## Teardown

```bash
./teardown.sh
```

You will be prompted to type the Spanner instance ID to confirm. All resources (database, instance, harness service account, key) are destroyed and the local `harness-sa-key.json` is removed.

---

## Multi-Region Example

To provision a multi-region instance instead of a regional one — for example a North-America config spanning multiple regions:

1. Edit `terraform/main.tf` and replace the `local.spanner_config` expression:

   ```hcl
   spanner_config = "nam3"   # or "eur3", "nam-eur-asia1", etc.
   ```

2. Multi-region configurations have higher minimum sizing and significantly higher cost — review the [Spanner instance configurations](https://cloud.google.com/spanner/docs/instance-configurations) reference before applying.

---

## Files

| File | Purpose |
|---|---|
| `terraform/main.tf` | Provider, Spanner instance, database, harness SA + IAM + key |
| `terraform/variables.tf` | All input variable declarations |
| `terraform/outputs.tf` | Project, instance, database, harness SA email and key emitted after apply |
| `deploy.sh` | Validates `.env`, exports `TF_VAR_*`, runs `terraform apply`, writes `harness-sa-key.json` |
| `teardown.sh` | Confirms intent, exports `TF_VAR_*`, runs `terraform destroy`, removes the key |
| `.env.example` | Template for all required environment variables |
| `.gitignore` | Excludes `.env`, Terraform state, the `.terraform/` cache, and `harness-sa-key.json` |

---

## Troubleshooting

**`Error: googleapi: Error 403: Permission ... denied`**
The provisioner service account is missing one of the required roles. Check that it has `roles/spanner.admin`, `roles/iam.serviceAccountAdmin`, `roles/iam.serviceAccountKeyAdmin`, and `roles/resourcemanager.projectIamAdmin` on the project.

**`Error: googleapi: Error 403: Cloud Spanner API has not been used in project ...`**
Enable the Spanner API: `gcloud services enable spanner.googleapis.com --project <project>`.

**`spanner_processing_units must be a multiple of 100 and at least 100`**
`SPANNER_PROCESSING_UNITS` in `.env` is below 100 or not a multiple of 100. Spanner additionally requires multiples of 1000 above 1000 — that constraint is enforced server-side.

**`Error: instance config "regional-..." does not exist`**
The `GCP_REGION` value does not correspond to a Spanner regional config. Confirm the region in the [Spanner instance configurations](https://cloud.google.com/spanner/docs/instance-configurations) list.

**`harness-sa-key.json` is missing after deploy**
Re-run `terraform -chdir=terraform output -raw harness_service_account_key | base64 -d > harness-sa-key.json` from this folder. The Terraform state still holds the key.

---

## Cost Notes

> **WARNING:** Cloud Spanner instances bill **continuously while provisioned**, regardless of query traffic. There is no scale-to-zero and no free tier for dedicated Spanner instances. Costs accrue per processing unit per hour for compute, plus separate per-GB-month charges for storage and per-GB charges for network egress.

- **100 PU** (the default in `.env.example`) is the smallest billable configuration. Refer to the [Spanner pricing page](https://cloud.google.com/spanner/pricing) for current rates in your region — at the time of writing, a regional 100-PU instance is on the order of single-digit USD per day.
- **Multi-region configurations** (`nam3`, `eur3`, `nam-eur-asia1`, …) have a higher minimum sizing and are several times more expensive per PU than regional. Read the pricing page before switching.
- **Storage and egress** are billed separately and persist even if you scale processing units down. Teardown removes both.
- **Always run `./teardown.sh`** when finished with a demo. Forgetting to tear down a Spanner instance is the single most common source of unexpected charges from this folder.
