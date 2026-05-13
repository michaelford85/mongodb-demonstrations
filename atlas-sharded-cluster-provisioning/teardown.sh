#!/usr/bin/env bash
# Destroys all resources created by deploy.sh (cluster, project, DB user).
set -euo pipefail

# ── Preflight ──────────────────────────────────────────────────────────────────

if ! command -v terraform &>/dev/null; then
  echo "ERROR: terraform not found."
  exit 1
fi

if [ ! -f .env ]; then
  echo "ERROR: .env not found."
  exit 1
fi

if [ ! -f terraform.tfstate ]; then
  echo "ERROR: terraform.tfstate not found. Nothing to destroy."
  exit 1
fi

# ── Load .env ──────────────────────────────────────────────────────────────────

set -a
# shellcheck source=/dev/null
source .env
set +a

# ── Confirmation ───────────────────────────────────────────────────────────────

echo ""
echo "WARNING: This will permanently destroy:"
echo "  Project : ${ATLAS_PROJECT_ID:-<unknown>}"
echo "  Cluster : ${CLUSTER_NAME:-<unknown>}"
echo ""
read -r -p "Type the cluster name to confirm destruction: " confirm

if [ "$confirm" != "${CLUSTER_NAME:-}" ]; then
  echo "Cluster name did not match. Aborting."
  exit 1
fi

# ── Export as TF_VAR_* ─────────────────────────────────────────────────────────

export TF_VAR_atlas_public_key="$ATLAS_PUBLIC_KEY"
export TF_VAR_atlas_private_key="$ATLAS_PRIVATE_KEY"
export TF_VAR_atlas_project_id="$ATLAS_PROJECT_ID"
export TF_VAR_cluster_name="$CLUSTER_NAME"
export TF_VAR_cluster_type="${CLUSTER_TYPE:-SHARDED}"
export TF_VAR_cluster_cloud_provider="$CLUSTER_CLOUD_PROVIDER"
export TF_VAR_cluster_instance_size="$CLUSTER_INSTANCE_SIZE"
export TF_VAR_mongodb_version="$MONGODB_VERSION"
export TF_VAR_cluster_shards="$CLUSTER_SHARDS"
export TF_VAR_cluster_search_nodes="$CLUSTER_SEARCH_NODES"
export TF_VAR_cluster_compute_autoscale_enabled="${CLUSTER_COMPUTE_AUTOSCALE_ENABLED:-true}"
export TF_VAR_cluster_compute_max_instance_size="${CLUSTER_COMPUTE_MAX_INSTANCE_SIZE:-}"
export TF_VAR_db_admin_user="$DB_ADMIN_USER"
export TF_VAR_db_admin_password="$DB_ADMIN_PASSWORD"

# ── Destroy ────────────────────────────────────────────────────────────────────

echo ""
echo "Destroying resources..."
terraform destroy -auto-approve

echo ""
echo "All resources destroyed."
