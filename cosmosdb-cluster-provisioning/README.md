# Azure Cosmos DB for NoSQL — Terraform provisioning (vector-search-ready)

This directory creates a small **Cosmos DB for NoSQL** account, database, and
container configured for vector search with **DiskANN**. It is the Azure
counterpart to the sibling `postgres-cluster-provisioning` demo and is
consumed by `pdf-rag-eval` for the Cosmos-vs-Atlas comparison.

## What gets created

| Resource                                     | Purpose                                                                 |
|----------------------------------------------|-------------------------------------------------------------------------|
| `azurerm_resource_group`                     | Owns every other resource so destroy is a single shot.                  |
| `azurerm_cosmosdb_account`                   | NoSQL account with the `EnableNoSQLVectorSearch` capability.            |
| `azurerm_cosmosdb_sql_database`              | Initial database (`ragdb` by default).                                  |
| `azurerm_cosmosdb_sql_container`             | Container partitioned on `/document_id`, autoscale to 1000 RU/s max.    |
| `azapi_update_resource.vector_policy`        | Layers on the `vectorEmbeddingPolicy` + DiskANN `vectorIndex`.          |

### Why two providers?

The `azurerm` provider doesn't yet expose `vector_embedding_policy` or
`vectorIndexes` on `azurerm_cosmosdb_sql_container`
([terraform-provider-azurerm#29597][1]). Until that lands we use the
`azapi` provider to PATCH the container with the vector policy immediately
after creation. Cosmos forbids changing the vector policy once the
container has data, so this update **must** run on an empty container —
Terraform's resource graph enforces ordering via `parent_id`.

[1]: https://github.com/hashicorp/terraform-provider-azurerm/issues/29597

### Design choices baked into this demo

| Choice                  | Value                  | Why                                                                                                                |
|-------------------------|------------------------|--------------------------------------------------------------------------------------------------------------------|
| API                     | Cosmos DB for NoSQL    | Native RU + physical-partition semantics, native DiskANN — matches the limits we want to compare against Atlas.    |
| Throughput              | Autoscale, max 1000 RU/s | Cheapest mode that still demonstrates 429s and partition behavior. Scales between 100 and 1000 RU/s.             |
| Partition key           | `/document_id`         | One logical partition per source PDF. Makes the 20 GB / 10K RU/s logical-partition ceiling easy to demonstrate.    |
| Vector path             | `/embedding`           | Excluded from the general indexing policy so it only lives in the vector index.                                    |
| Vector dimensions       | 1024                   | Matches `voyage-4-large` default output.                                                                           |
| Vector index            | DiskANN                | Lowest RU cost / latency at scale; quantizedFlat and flat are also valid via `TF_VAR_vector_index_type`.           |
| Auth                    | Account key            | Exposed via sensitive Terraform output, mirroring how the postgres demo exposes the master password.               |

## Prerequisites

- **Terraform** ≥ 1.5 (`brew install terraform`).
- **Azure CLI** authenticated to the target subscription
  (`az login` then `az account show` should succeed).
- A subscription where the Cosmos DB resource provider is registered
  (`az provider register --namespace Microsoft.DocumentDB` if not).
- Your laptop's public IPv4 — Cosmos's IP allow-list is the only thing
  letting your client reach the data plane.

> Cost note: an autoscale container with `max_throughput = 1000` floors at
> 100 RU/s when idle, billed by the hour. Roughly USD ~$24/month if left
> running, plus a few cents of storage. Use `./teardown.sh` when done.

## Setup

```bash
cd cosmosdb-cluster-provisioning

# 1. Copy the env template and fill in real values.
cp .env.example .env
$EDITOR .env
#   At minimum, set:
#     ARM_SUBSCRIPTION_ID            (az account show --query id -o tsv)
#     TF_VAR_account_name            (globally unique, 3-44 chars)
#     TF_VAR_allowed_ip_addresses    (your laptop's public IP)

# 2. Provision. setup.sh sources .env, verifies `az login`, runs init +
#    apply, and prints non-sensitive connection details.
./setup.sh
```

After `setup.sh` finishes you will see a `connection_string_template`
output of the form:

```
AccountEndpoint=https://<your-account>.documents.azure.com:443/;AccountKey=<PRIMARY_KEY>;
```

To pull the **full** connection string (including the key) into a shell
variable without echoing it:

```bash
export COSMOS_CONN_STR="$(terraform output -raw connection_string)"
export COSMOS_KEY="$(terraform output -raw primary_key)"
```

`terraform output -raw` reads the value directly from state; it is the
recommended way to consume a `sensitive = true` output.

### Verifying the vector policy landed

```bash
az cosmosdb sql container show \
  --account-name "$TF_VAR_account_name" \
  --resource-group "${TF_VAR_resource_group_name:-cosmos-vector-demo-rg}" \
  --database-name "${TF_VAR_database_name:-ragdb}" \
  --name         "${TF_VAR_container_name:-chunks}" \
  --query "resource.vectorEmbeddingPolicy"
```

You should see one entry with `path: /embedding`, `dataType: float32`,
`dimensions: 1024`, `distanceFunction: cosine`.

## Variables

All variables can be set via `TF_VAR_*` environment variables. The ones in
`.env.example` are the ones you are most likely to change.

| Variable                       | Default                      | Notes                                                                  |
|--------------------------------|------------------------------|------------------------------------------------------------------------|
| `location`                     | `eastus`                     | Override with `TF_VAR_location`.                                       |
| `resource_group_name`          | `cosmos-vector-demo-rg`      | Created and destroyed by Terraform.                                    |
| `account_name`                 | (required)                   | Globally unique, 3-44 chars, lowercase letters/digits/hyphens.         |
| `database_name`                | `ragdb`                      | Initial database.                                                      |
| `container_name`               | `chunks`                     | Vector-enabled container.                                              |
| `partition_key_path`           | `/document_id`               | One logical partition per source PDF.                                  |
| `vector_path`                  | `/embedding`                 | Excluded from the general indexing policy.                             |
| `vector_dimensions`            | `1024`                       | Matches voyage-4-large default.                                        |
| `vector_distance_function`     | `cosine`                     | Or `dotproduct` / `euclidean`.                                         |
| `vector_index_type`            | `diskANN`                    | Or `flat` / `quantizedFlat`.                                           |
| `autoscale_max_throughput`     | `1000`                       | Minimum allowed by Cosmos autoscale.                                   |
| `consistency_level`            | `Session`                    | Default Cosmos consistency.                                            |
| `allowed_ip_addresses`         | (required)                   | List of public IPs/CIDRs; `0.0.0.0/0` is rejected.                     |

## Teardown

```bash
./teardown.sh
```

Runs `terraform destroy -auto-approve`, removing the container, database,
account, and resource group.

## Security notes

- `.env` and `*.tfstate*` are in `.gitignore`. Never commit them.
- The IP allow-list refuses `0.0.0.0/0` to prevent accidental internet
  exposure of the data plane.
- `connection_string`, `primary_key`, and `primary_readonly_key` outputs
  are marked `sensitive = true` and redacted from `apply` logs.
- Local Terraform state contains the account keys. For shared use, switch
  to a remote backend (Azure Storage + state locking) with appropriate
  RBAC.

## Troubleshooting

- **`MissingSubscriptionRegistration`** — register the provider once with
  `az provider register --namespace Microsoft.DocumentDB`.
- **`Conflict: account name already exists`** — Cosmos account names are
  globally unique across all of Azure. Pick a more specific
  `TF_VAR_account_name`.
- **Client times out / `Forbidden`** — your public IP changed. Update
  `TF_VAR_allowed_ip_addresses` and re-run `./setup.sh`.
- **`The vector embedding policy cannot be modified`** — the azapi update
  ran against a container that already had data. Destroy and recreate the
  container; the policy is immutable post-write.
