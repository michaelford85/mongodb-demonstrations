#!/usr/bin/env bash
# Creates a regional Spanner instance and database from the values in .env.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/terraform"
HARNESS_KEY_FILE="$SCRIPT_DIR/harness-sa-key.json"

# ── Preflight ──────────────────────────────────────────────────────────────────

if ! command -v terraform &>/dev/null; then
  echo "ERROR: terraform not found. Install it from https://developer.hashicorp.com/terraform/install"
  exit 1
fi

if ! command -v jq &>/dev/null; then
  echo "ERROR: jq not found. Install it with: brew install jq  (or your package manager)"
  exit 1
fi

if [ ! -f "$SCRIPT_DIR/.env" ]; then
  echo "ERROR: .env not found. Copy .env.example to .env and fill in your values."
  exit 1
fi

# ── Load .env ──────────────────────────────────────────────────────────────────

set -a
# shellcheck source=/dev/null
source "$SCRIPT_DIR/.env"
set +a

# ── Validate required variables ────────────────────────────────────────────────

required_vars=(
  GOOGLE_APPLICATION_CREDENTIALS
  GCP_PROJECT_ID GCP_REGION
  SPANNER_INSTANCE_ID SPANNER_DATABASE_ID
  SPANNER_PROCESSING_UNITS SPANNER_DIALECT
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

if [ ! -f "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
  echo "ERROR: GOOGLE_APPLICATION_CREDENTIALS does not point to an existing file:"
  echo "  $GOOGLE_APPLICATION_CREDENTIALS"
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

# ── Deploy ─────────────────────────────────────────────────────────────────────

echo ""
echo "Deploying Spanner instance:"
echo "  Project  : $GCP_PROJECT_ID"
echo "  Region   : $GCP_REGION (config: regional-$GCP_REGION)"
echo "  Instance : $SPANNER_INSTANCE_ID ($SPANNER_PROCESSING_UNITS PU)"
echo "  Database : $SPANNER_DATABASE_ID ($SPANNER_DIALECT)"
echo ""

terraform -chdir="$TF_DIR" init -upgrade
terraform -chdir="$TF_DIR" apply -auto-approve

# ── Emit harness service-account key ──────────────────────────────────────────

echo ""
echo "Writing harness service-account key to: $HARNESS_KEY_FILE"
terraform -chdir="$TF_DIR" output -raw harness_service_account_key | base64 -d > "$HARNESS_KEY_FILE"
chmod 600 "$HARNESS_KEY_FILE"

echo ""
echo "Spanner is provisioned. Harness can authenticate via:"
echo "  export GOOGLE_APPLICATION_CREDENTIALS=$HARNESS_KEY_FILE"
