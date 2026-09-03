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
  CLUSTER_NUM_REGIONS CLUSTER_REGIONS
  CLUSTER_SEARCH_NODES
  DB_ADMIN_USER DB_ADMIN_PASSWORD
  DB_APP_USER DB_APP_PASSWORD
  DB_MONITOR_USER DB_MONITOR_PASSWORD
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

# Validate CLUSTER_REGIONS is valid JSON and count matches CLUSTER_NUM_REGIONS
if ! echo "$CLUSTER_REGIONS" | jq empty 2>/dev/null; then
  echo "ERROR: CLUSTER_REGIONS is not valid JSON."
  exit 1
fi

actual_count=$(echo "$CLUSTER_REGIONS" | jq 'length')
if [ "$actual_count" -ne "$CLUSTER_NUM_REGIONS" ]; then
  echo "ERROR: CLUSTER_NUM_REGIONS=$CLUSTER_NUM_REGIONS but CLUSTER_REGIONS contains $actual_count entries."
  exit 1
fi

# ── Storage class ──────────────────────────────────────────────────────────────
# CLUSTER_STORAGE_CLASS is optional — default SSD. NVME selects local NVMe SSDs
# by appending the _NVME suffix to the instance size in Terraform.
CLUSTER_STORAGE_CLASS="$(echo "${CLUSTER_STORAGE_CLASS:-SSD}" | tr '[:lower:]' '[:upper:]')"
if [ "$CLUSTER_STORAGE_CLASS" != "SSD" ] && [ "$CLUSTER_STORAGE_CLASS" != "NVME" ]; then
  echo "ERROR: CLUSTER_STORAGE_CLASS must be SSD or NVME (got: $CLUSTER_STORAGE_CLASS)."
  exit 1
fi

CLUSTER_DISK_SIZE_GB="${CLUSTER_DISK_SIZE_GB:-0}"

# Local NVMe is only offered on AWS and Azure, and its disk capacity is fixed
# per tier — Atlas rejects an explicit disk size.
if [ "$CLUSTER_STORAGE_CLASS" = "NVME" ] || [[ "$(echo "$CLUSTER_INSTANCE_SIZE" | tr '[:lower:]' '[:upper:]')" == *_NVME ]]; then
  if [ "$CLUSTER_CLOUD_PROVIDER" != "AWS" ] && [ "$CLUSTER_CLOUD_PROVIDER" != "AZURE" ]; then
    echo "ERROR: local NVMe storage is only offered on AWS and AZURE (got: $CLUSTER_CLOUD_PROVIDER)."
    exit 1
  fi
  if [ "$CLUSTER_DISK_SIZE_GB" != "0" ]; then
    echo "ERROR: CLUSTER_DISK_SIZE_GB must be 0 with local NVMe storage — Atlas fixes disk capacity per NVMe tier."
    exit 1
  fi
fi

# ── Export as TF_VAR_* ─────────────────────────────────────────────────────────

export TF_VAR_atlas_public_key="$ATLAS_PUBLIC_KEY"
export TF_VAR_atlas_private_key="$ATLAS_PRIVATE_KEY"
export TF_VAR_atlas_project_id="$ATLAS_PROJECT_ID"
export TF_VAR_cluster_name="$CLUSTER_NAME"
export TF_VAR_cluster_cloud_provider="$CLUSTER_CLOUD_PROVIDER"
export TF_VAR_cluster_instance_size="$CLUSTER_INSTANCE_SIZE"
export TF_VAR_cluster_storage_class="$CLUSTER_STORAGE_CLASS"
export TF_VAR_cluster_disk_size_gb="$CLUSTER_DISK_SIZE_GB"
export TF_VAR_mongodb_version="$MONGODB_VERSION"
export TF_VAR_cluster_regions="$CLUSTER_REGIONS"
export TF_VAR_cluster_search_nodes="$CLUSTER_SEARCH_NODES"
export TF_VAR_cluster_compute_autoscale_enabled="${CLUSTER_COMPUTE_AUTOSCALE_ENABLED:-true}"
export TF_VAR_cluster_compute_max_instance_size="${CLUSTER_COMPUTE_MAX_INSTANCE_SIZE:-}"
export TF_VAR_db_admin_user="$DB_ADMIN_USER"
export TF_VAR_db_admin_password="$DB_ADMIN_PASSWORD"
export TF_VAR_db_app_user="$DB_APP_USER"
export TF_VAR_db_app_password="$DB_APP_PASSWORD"
export TF_VAR_db_monitor_user="$DB_MONITOR_USER"
export TF_VAR_db_monitor_password="$DB_MONITOR_PASSWORD"

# ── Deploy ─────────────────────────────────────────────────────────────────────

echo ""
echo "Deploying Atlas cluster:"
echo "  Project : $ATLAS_PROJECT_ID"
echo "  Cluster : $CLUSTER_NAME ($CLUSTER_CLOUD_PROVIDER / $CLUSTER_INSTANCE_SIZE)"
echo "  Storage : $CLUSTER_STORAGE_CLASS ($([ "$CLUSTER_DISK_SIZE_GB" = "0" ] && echo "Atlas default size" || echo "${CLUSTER_DISK_SIZE_GB} GB"))"
echo "  Regions : $CLUSTER_NUM_REGIONS"
echo "  MongoDB : $MONGODB_VERSION"
echo "  Search nodes: $CLUSTER_SEARCH_NODES"
echo ""

terraform init -upgrade
terraform apply -auto-approve

echo ""
echo "Cluster is provisioning. Connection strings are shown above."
echo "It typically takes 5–10 minutes for Atlas to fully provision a new cluster."
