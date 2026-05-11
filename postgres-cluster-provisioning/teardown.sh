#!/usr/bin/env bash
# Destroy every resource created by setup.sh.
set -euo pipefail

cd "$(dirname "$0")"

if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
else
  echo "WARNING: .env not found; relying on existing shell environment." >&2
fi

echo "==> terraform destroy"
terraform destroy -auto-approve -input=false

echo "==> Done. The Aurora cluster and its supporting resources have been removed."
