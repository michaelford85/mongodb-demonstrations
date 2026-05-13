#!/usr/bin/env bash
# Creates an Atlas project and cluster from the values in .env.
set -euo pipefail

# ── Preflight ──────────────────────────────────────────────────────────────────

if ! command -v terraform &>/dev/null; then
  echo "ERROR: terraform not found. Install it from https://developer.hashicorp.com/terraform/install"
  exit 1
fi

if ! command -v jq &>/dev/null; then
  echo "ERROR: jq not found. Install it with: brew install jq  (or your package manager)"
  exit 1
fi

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Copy .env.example to .env and fill in your values."
  exit 1
fi

# ── Load .env ──────────────────────────────────────────────────────────────────

set -a
# shellcheck source=/dev/null
source .env
set +a

# ── Validate required variables ────────────────────────────────────────────────

required_vars=(
  ATLAS_PUBLIC_KEY ATLAS_PRIVATE_KEY
  ATLAS_PROJECT_ID CLUSTER_NAME
  CLUSTER_CLOUD_PROVIDER CLUSTER_INSTANCE_SIZE MONGODB_VERSION
  CLUSTER_NUM_SHARDS CLUSTER_SHARDS
  CLUSTER_SEARCH_NODES
  DB_ADMIN_USER DB_ADMIN_PASSWORD
)

missing=()
for var in "${required_vars[@]}"; do
  if [ -z "${!var:-}" ]; then
    missing+=("$var")
  fi
done

if [ ${#missing[@]} -gt 0 ]; then
  echo "ERROR: Missing required variables in .env:"
  for var in "${missing[@]}"; do
    echo "  - $var"
  done
  exit 1
fi

# Validate CLUSTER_SHARDS is valid JSON and count matches CLUSTER_NUM_SHARDS
if ! echo "$CLUSTER_SHARDS" | jq empty 2>/dev/null; then
  echo "ERROR: CLUSTER_SHARDS is not valid JSON."
  exit 1
fi

actual_count=$(echo "$CLUSTER_SHARDS" | jq 'length')
if [ "$actual_count" -ne "$CLUSTER_NUM_SHARDS" ]; then
  echo "ERROR: CLUSTER_NUM_SHARDS=$CLUSTER_NUM_SHARDS but CLUSTER_SHARDS contains $actual_count entries."
  exit 1
fi

# Each shard must declare at least one region_config
shards_missing_regions=$(echo "$CLUSTER_SHARDS" | jq '[.[] | select((.region_configs // []) | length == 0)] | length')
if [ "$shards_missing_regions" -ne 0 ]; then
  echo "ERROR: Every shard in CLUSTER_SHARDS must include a non-empty region_configs array."
  exit 1
fi

# CLUSTER_TYPE is optional — default SHARDED. Validate the value if provided.
CLUSTER_TYPE="${CLUSTER_TYPE:-SHARDED}"
if [ "$CLUSTER_TYPE" != "SHARDED" ] && [ "$CLUSTER_TYPE" != "GEOSHARDED" ]; then
  echo "ERROR: CLUSTER_TYPE must be SHARDED or GEOSHARDED (got: $CLUSTER_TYPE)."
  exit 1
fi

# When CLUSTER_TYPE=SHARDED, Atlas requires every shard to have the same
# region topology. Catch that here with a clearer error than the API gives.
if [ "$CLUSTER_TYPE" = "SHARDED" ]; then
  distinct_topologies=$(echo "$CLUSTER_SHARDS" | jq '[.[] | .region_configs] | map(tostring) | unique | length')
  if [ "$distinct_topologies" -gt 1 ]; then
    echo "ERROR: CLUSTER_TYPE=SHARDED requires every shard to have identical region_configs."
    echo "       Either align the region_configs across all shards, or set CLUSTER_TYPE=GEOSHARDED"
    echo "       (each shard then lives in its own zone and may use different regions)."
    exit 1
  fi
fi

# ── Export as TF_VAR_* ─────────────────────────────────────────────────────────

export TF_VAR_atlas_public_key="$ATLAS_PUBLIC_KEY"
export TF_VAR_atlas_private_key="$ATLAS_PRIVATE_KEY"
export TF_VAR_atlas_project_id="$ATLAS_PROJECT_ID"
export TF_VAR_cluster_name="$CLUSTER_NAME"
export TF_VAR_cluster_type="$CLUSTER_TYPE"
export TF_VAR_cluster_cloud_provider="$CLUSTER_CLOUD_PROVIDER"
export TF_VAR_cluster_instance_size="$CLUSTER_INSTANCE_SIZE"
export TF_VAR_mongodb_version="$MONGODB_VERSION"
export TF_VAR_cluster_shards="$CLUSTER_SHARDS"
export TF_VAR_cluster_search_nodes="$CLUSTER_SEARCH_NODES"
export TF_VAR_cluster_compute_autoscale_enabled="${CLUSTER_COMPUTE_AUTOSCALE_ENABLED:-true}"
export TF_VAR_cluster_compute_max_instance_size="${CLUSTER_COMPUTE_MAX_INSTANCE_SIZE:-}"
export TF_VAR_db_admin_user="$DB_ADMIN_USER"
export TF_VAR_db_admin_password="$DB_ADMIN_PASSWORD"

# ── Deploy ─────────────────────────────────────────────────────────────────────

echo ""
echo "Deploying Atlas sharded cluster:"
echo "  Project : $ATLAS_PROJECT_ID"
echo "  Cluster : $CLUSTER_NAME ($CLUSTER_CLOUD_PROVIDER / $CLUSTER_INSTANCE_SIZE)"
echo "  Type    : $CLUSTER_TYPE"
echo "  Shards  : $CLUSTER_NUM_SHARDS"
echo "  MongoDB : $MONGODB_VERSION"
echo "  Search nodes: $CLUSTER_SEARCH_NODES"
echo ""

terraform init -upgrade
terraform apply -auto-approve

echo ""
echo "Cluster is provisioning. Connection strings are shown above."
echo "It typically takes 5–10 minutes for Atlas to fully provision a new cluster."
