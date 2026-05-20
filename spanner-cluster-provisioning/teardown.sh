#!/usr/bin/env bash
# Destroys all resources created by deploy.sh (Spanner database, instance,
# harness service account and its key).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/terraform"
HARNESS_KEY_FILE="$SCRIPT_DIR/harness-sa-key.json"

# ── Preflight ──────────────────────────────────────────────────────────────────

if ! command -v terraform &>/dev/null; then
  echo "ERROR: terraform not found."
  exit 1
fi

if [ ! -f "$SCRIPT_DIR/.env" ]; then
  echo "ERROR: .env not found."
  exit 1
fi

if [ ! -f "$TF_DIR/terraform.tfstate" ]; then
  echo "ERROR: terraform/terraform.tfstate not found. Nothing to destroy."
  exit 1
fi

# ── Load .env ──────────────────────────────────────────────────────────────────

set -a
# shellcheck source=/dev/null
source "$SCRIPT_DIR/.env"
set +a

# ── Confirmation ───────────────────────────────────────────────────────────────

echo ""
echo "WARNING: This will permanently destroy:"
echo "  Project  : ${GCP_PROJECT_ID:-<unknown>}"
echo "  Instance : ${SPANNER_INSTANCE_ID:-<unknown>}"
echo "  Database : ${SPANNER_DATABASE_ID:-<unknown>}"
echo ""
read -r -p "Type the Spanner instance ID to confirm destruction: " confirm

if [ "$confirm" != "${SPANNER_INSTANCE_ID:-}" ]; then
  echo "Instance ID did not match. Aborting."
  exit 1
fi

# ── Export as TF_VAR_* ─────────────────────────────────────────────────────────

export GOOGLE_APPLICATION_CREDENTIALS
export TF_VAR_gcp_project_id="$GCP_PROJECT_ID"
export TF_VAR_gcp_region="$GCP_REGION"
export TF_VAR_spanner_instance_id="$SPANNER_INSTANCE_ID"
export TF_VAR_spanner_database_id="$SPANNER_DATABASE_ID"
export TF_VAR_spanner_processing_units="$SPANNER_PROCESSING_UNITS"
export TF_VAR_spanner_dialect="$SPANNER_DIALECT"

# ── Destroy ────────────────────────────────────────────────────────────────────

echo ""
echo "Destroying resources..."
terraform -chdir="$TF_DIR" destroy -auto-approve

# Remove the locally materialised harness key file.
if [ -f "$HARNESS_KEY_FILE" ]; then
  rm -f "$HARNESS_KEY_FILE"
  echo "Removed $HARNESS_KEY_FILE"
fi

echo ""
echo "All resources destroyed."
