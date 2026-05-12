#!/usr/bin/env bash
# Provision the Cosmos DB for NoSQL account, database, and vector-enabled
# container. Idempotent: re-running after a successful apply is a no-op.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Copy .env.example to .env and fill it in." >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a; source .env; set +a

: "${ARM_SUBSCRIPTION_ID:?ARM_SUBSCRIPTION_ID is empty; edit .env}"
: "${TF_VAR_account_name:?TF_VAR_account_name is empty; edit .env}"
: "${TF_VAR_allowed_ip_addresses:?TF_VAR_allowed_ip_addresses is empty; edit .env}"

# Confirm an Azure CLI session is active. The azurerm and azapi providers
# both pick up credentials from `az login` when ARM_SUBSCRIPTION_ID is set.
if ! az account show >/dev/null 2>&1; then
  echo "ERROR: no active Azure CLI session. Run 'az login' first." >&2
  exit 1
fi

echo "==> terraform init"
terraform init -input=false

echo "==> terraform apply"
terraform apply -auto-approve -input=false

echo
echo "==> Account ready. Non-sensitive connection details:"
terraform output connection_string_template
terraform output endpoint
terraform output database_name
terraform output container_name

cat <<'EOF'

The container was created with the DiskANN vector policy applied via the
azapi provider. To export the full connection string into your shell
without printing it:

  export COSMOS_CONN_STR="$(terraform output -raw connection_string)"
  export COSMOS_KEY="$(terraform output -raw primary_key)"

The sibling pdf-rag-eval demo reads these values from its own .env.
EOF
