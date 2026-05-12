#!/usr/bin/env bash
# Provision the Azure Storage Account and PDF blob container.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Copy .env.example to .env and fill it in." >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a; source .env; set +a

: "${ARM_SUBSCRIPTION_ID:?ARM_SUBSCRIPTION_ID is empty; edit .env}"
: "${TF_VAR_storage_account_name:?TF_VAR_storage_account_name is empty; edit .env}"
: "${TF_VAR_allowed_ip_addresses:?TF_VAR_allowed_ip_addresses is empty; edit .env}"

# Refuse the unedited template values. Without these guards,
# terraform 1.15.x panics on the malformed list literal that bash
# produces from an unquoted JSON value in .env.example.
if [ "$ARM_SUBSCRIPTION_ID" = "00000000-0000-0000-0000-000000000000" ]; then
  echo "ERROR: ARM_SUBSCRIPTION_ID is still the placeholder. Edit .env." >&2
  exit 1
fi
if [ "$TF_VAR_storage_account_name" = "changeme0pdfrageval" ]; then
  echo "ERROR: TF_VAR_storage_account_name is still the placeholder. Edit .env." >&2
  exit 1
fi
if [[ "$TF_VAR_allowed_ip_addresses" == *203.0.113.42* ]]; then
  echo "ERROR: TF_VAR_allowed_ip_addresses is still the placeholder. Edit .env." >&2
  exit 1
fi
if [[ "$TF_VAR_allowed_ip_addresses" != \[\"*\"\]* ]]; then
  echo "ERROR: TF_VAR_allowed_ip_addresses must be wrapped in single quotes" >&2
  echo "       in .env so the inner double quotes survive sourcing, e.g.:" >&2
  echo "         TF_VAR_allowed_ip_addresses='[\"1.2.3.4\"]'" >&2
  exit 1
fi

if ! az account show >/dev/null 2>&1; then
  echo "ERROR: no active Azure CLI session. Run 'az login' first." >&2
  exit 1
fi

echo "==> terraform init"
terraform init -input=false

echo "==> terraform apply"
terraform apply -auto-approve -input=false

echo
echo "==> Storage account ready. Non-sensitive connection details:"
terraform output connection_string_template
terraform output blob_endpoint
terraform output container_name

cat <<'EOF'

To export the storage connection string into the parent .env file (so
upload_blobs.py and embed_and_load.py pick it up):

  STORAGE_CONN_STR="$(terraform output -raw connection_string)"
  echo "AZURE_STORAGE_CONNECTION_STRING=$STORAGE_CONN_STR" >> ../.env

The parent .env is gitignored.
EOF
