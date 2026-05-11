#!/usr/bin/env bash
# Provision the Aurora PostgreSQL cluster. Idempotent: re-running after a
# successful apply is a no-op.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Copy .env.example to .env and fill it in." >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a; source .env; set +a

: "${TF_VAR_db_admin_password:?TF_VAR_db_admin_password is empty; edit .env}"
: "${TF_VAR_allowed_cidr_blocks:?TF_VAR_allowed_cidr_blocks is empty; edit .env}"

echo "==> terraform init"
terraform init -input=false

echo "==> terraform apply"
terraform apply -auto-approve -input=false

echo
echo "==> Cluster ready. Non-sensitive connection details:"
terraform output connection_string_template
terraform output psql_command

cat <<'EOF'

To export the full connection string into your shell without printing it:

  export PG_CONN_STR="$(terraform output -raw connection_string)"

To enable pgvector once the cluster is reachable:

  psql "$PG_CONN_STR" -c 'CREATE EXTENSION IF NOT EXISTS vector;'
EOF
