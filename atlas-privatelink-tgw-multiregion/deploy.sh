#!/usr/bin/env bash
# Builds the AWS side of the lab from the values in .env.
#
# Creates nothing in Atlas and reads nothing from Atlas. The Atlas cluster, its
# project and its private endpoint services must already exist.
set -euo pipefail

# ── Preflight ──────────────────────────────────────────────────────────────────

for tool in terraform jq aws; do
  if ! command -v "$tool" &>/dev/null; then
    echo "ERROR: $tool not found."
    exit 1
  fi
done

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
  NAME_PREFIX
  TAG_PROJECT TAG_ENVIRONMENT TAG_OWNER TAG_PURPOSE
  HUBS CLIENT
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

if [ "$TAG_OWNER" = "<your-name-or-team>" ]; then
  echo "ERROR: TAG_OWNER still holds the placeholder from .env.example."
  exit 1
fi

for json_var in HUBS CLIENT; do
  if ! echo "${!json_var}" | jq empty 2>/dev/null; then
    echo "ERROR: $json_var is not valid JSON."
    exit 1
  fi
done

for json_var in EXTRA_TAGS TEST_PORTS TEST_PORT_SCAN SPOKES; do
  value="${!json_var:-}"
  if [ -n "$value" ] && ! echo "$value" | jq empty 2>/dev/null; then
    echo "ERROR: $json_var is not valid JSON."
    exit 1
  fi
done

# The example service names are deliberately fake. Catch them before Terraform
# spends ten minutes building a hub around an endpoint that can never connect.
placeholder_services=$(echo "$HUBS" |
  jq -r '[.[].atlas_endpoint_services // {} | .[]] | map(select(. == "com.amazonaws.vpce.eu-west-1.vpce-svc-0123456789abcdef0" or . == "com.amazonaws.vpce.eu-central-1.vpce-svc-abcdef01234567890")) | .[]')

if [ -n "$placeholder_services" ]; then
  echo "ERROR: HUBS still contains the placeholder Atlas endpoint service names from .env.example:"
  echo "$placeholder_services" | sed 's/^/  - /'
  echo ""
  echo "Read the real names from Atlas UI -> Network Access -> Private Endpoint,"
  echo "one per Atlas project-region that the replica set has nodes in."
  exit 1
fi

# Secrets must not reach Terraform. Nothing in this lab needs them.
for forbidden in ATLAS_PUBLIC_KEY ATLAS_PRIVATE_KEY ATLAS_URI MONGODB_URI AWS_SECRET_ACCESS_KEY; do
  if [ -n "${!forbidden:-}" ] && grep -q "^[[:space:]]*${forbidden}=" .env 2>/dev/null; then
    echo "ERROR: .env sets $forbidden. This lab never needs it, and anything in .env"
    echo "       that this script exports could end up in Terraform state."
    exit 1
  fi
done

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "ERROR: no usable AWS credentials. Try: aws sso login --profile \"${AWS_PROFILE:-default}\""
  exit 1
fi

# ── Spoke preflight ────────────────────────────────────────────────────────────
# Only when SPOKES is non-empty. Without these checks a misconfigured spoke
# fails several minutes into the apply, after both Transit Gateways exist.
#
# SPOKES is normalised here rather than in the export block below, because this
# runs first and `set -u` would abort on an unset variable.

SPOKES="${SPOKES:-}"
[ -n "$SPOKES" ] || SPOKES='{}'

spoke_preflight_count=$(echo "$SPOKES" | jq -r 'length')

if [ "$spoke_preflight_count" -gt 0 ]; then
  echo "Checking cross-account prerequisites for $spoke_preflight_count application account(s)..."

  # 1. RAM sharing with the organisation. Only the management account can read
  #    this, so an access error is reported as a warning rather than a failure.
  ram_state=$(aws organizations list-aws-service-access-for-organization \
    --query "EnabledServicePrincipals[?ServicePrincipal=='ram.amazonaws.com'].ServicePrincipal" \
    --output text 2>/dev/null || echo "UNKNOWN")

  if [ "$ram_state" = "UNKNOWN" ]; then
    echo "  WARNING: could not check RAM organisation sharing from this account."
    echo "           If the Transit Gateway share is not accepted, run this in the"
    echo "           management account: aws ram enable-sharing-with-aws-organization"
  elif [ -z "$ram_state" ]; then
    echo ""
    echo "ERROR: RAM sharing with the organisation is not enabled, so the spoke"
    echo "       accounts will never accept the Transit Gateway share."
    echo ""
    echo "  Run once, in the organisation's MANAGEMENT account:"
    echo "    aws ram enable-sharing-with-aws-organization"
    echo ""
    echo "  If the spoke accounts are NOT in this organisation, set"
    echo "  RAM_ALLOW_EXTERNAL_PRINCIPALS=true in .env and accept the share by hand."
    exit 1
  else
    echo "  RAM organisation sharing: enabled"
  fi

  # 2. Every spoke role must actually be assumable from here.
  while IFS=$'\t' read -r spoke_key spoke_account spoke_role; do
    [ -z "${spoke_role:-}" ] && continue
    if assumed=$(aws sts assume-role \
      --role-arn "$spoke_role" \
      --role-session-name "${NAME_PREFIX}-preflight" \
      --duration-seconds 900 \
      --query 'AssumedRoleUser.Arn' --output text 2>&1); then
      echo "  spoke $spoke_key ($spoke_account): role assumable"
    else
      echo ""
      echo "ERROR: cannot assume the role for spoke \"$spoke_key\":"
      echo "         $spoke_role"
      echo "       $assumed"
      echo ""
      echo "  In an AWS Organization, OrganizationAccountAccessRole exists in member"
      echo "  accounts and trusts the MANAGEMENT account. Check that:"
      echo "    - you are running as the management account (or a role it allows)"
      echo "    - account $spoke_account is a member of this organisation"
      echo "    - the role name is right for that account"
      exit 1
    fi
  done < <(echo "$SPOKES" | jq -r 'to_entries[] | [.key, .value.account_id, .value.role_arn] | @tsv')

  echo ""
fi

# ── Internet egress toggle ─────────────────────────────────────────────────────
# CLIENT_INTERNET_EGRESS is merged into the CLIENT object so the NAT gateway can
# be turned on for the mongosh install and off again afterwards without editing
# JSON. It never affects the Atlas path.

CLIENT_INTERNET_EGRESS="$(echo "${CLIENT_INTERNET_EGRESS:-true}" | tr '[:upper:]' '[:lower:]')"
if [ "$CLIENT_INTERNET_EGRESS" != "true" ] && [ "$CLIENT_INTERNET_EGRESS" != "false" ]; then
  echo "ERROR: CLIENT_INTERNET_EGRESS must be true or false (got: $CLIENT_INTERNET_EGRESS)."
  exit 1
fi

CLIENT=$(echo "$CLIENT" | jq --argjson egress "$CLIENT_INTERNET_EGRESS" '.internet_egress_enabled = $egress')

if [ "$CLIENT_INTERNET_EGRESS" = "true" ] && [ "$(echo "$CLIENT" | jq -r '.nat_subnet_cidr // ""')" = "" ]; then
  echo "ERROR: CLIENT_INTERNET_EGRESS=true needs nat_subnet_cidr in CLIENT."
  echo "       A /28 that does not overlap the other subnets is plenty."
  exit 1
fi

# ── Export as TF_VAR_* ─────────────────────────────────────────────────────────

EXTRA_TAGS="${EXTRA_TAGS:-}"
[ -n "$EXTRA_TAGS" ] || EXTRA_TAGS="{}"

export TF_VAR_name_prefix="$NAME_PREFIX"
export TF_VAR_tag_project="$TAG_PROJECT"
export TF_VAR_tag_environment="$TAG_ENVIRONMENT"
export TF_VAR_tag_owner="$TAG_OWNER"
export TF_VAR_tag_purpose="$TAG_PURPOSE"
export TF_VAR_extra_tags="$EXTRA_TAGS"
export TF_VAR_hubs="$HUBS"
export TF_VAR_client="$CLIENT"
export TF_VAR_allow_single_az_endpoints="${ALLOW_SINGLE_AZ_ENDPOINTS:-false}"
# Defaults are assigned on their own lines, not inside ${VAR:-...}: brace and
# backslash escaping inside a parameter expansion differs between shells, and
# a stray backslash reaches Terraform as an invalid character.
TEST_PORTS="${TEST_PORTS:-}"
[ -n "$TEST_PORTS" ] || TEST_PORTS='[27017]'

TEST_PORT_SCAN="${TEST_PORT_SCAN:-}"
[ -n "$TEST_PORT_SCAN" ] || TEST_PORT_SCAN='{"start": 1024, "end": 1060}'

SPOKES="${SPOKES:-}"
[ -n "$SPOKES" ] || SPOKES='{}'

export TF_VAR_spokes="$SPOKES"
export TF_VAR_ram_allow_external_principals="${RAM_ALLOW_EXTERNAL_PRINCIPALS:-false}"
export TF_VAR_test_ports="$TEST_PORTS"
export TF_VAR_test_port_scan_range="$TEST_PORT_SCAN"
export TF_VAR_mongosh_s3_uri="${MONGOSH_S3_URI:-}"

# ── Summary and cost warning ───────────────────────────────────────────────────

region_a=$(echo "$HUBS" | jq -r '.a.aws_region')
region_b=$(echo "$HUBS" | jq -r '.b.aws_region')
eni_count=$(echo "$HUBS" | jq -r '[.[] | (.atlas_endpoint_services | length) * (.subnet_cidrs | length)] | add')
tgw_count=$(echo "$HUBS" | jq -r 'length')
spoke_count=$(echo "$SPOKES" | jq -r 'length')   # already normalised above

if [ "$CLIENT_INTERNET_EGRESS" = "true" ]; then
  nat_cost_line="1 NAT gateway and its elastic IP (per hour, plus per GB),"
else
  nat_cost_line="no NAT gateway,"
fi

cat <<SUMMARY

Deploying the Atlas PrivateLink + Transit Gateway multi-region lab

  Prefix        : $NAME_PREFIX
  Owner         : $TAG_OWNER
  Region A      : $region_a   (client VPC, hub VPC, Transit Gateway)
  Region B      : $region_b   (hub VPC, Transit Gateway)
  Peering       : direct A <-> B, explicit routes in both directions
  Endpoint ENIs : $eni_count  (billed per ENI per hour)
  Spoke accounts: $spoke_count  (consume the same endpoints; add none of their own)
  NAT egress    : $CLIENT_INTERNET_EGRESS  (mongosh install only; MongoDB ports
                  are never allowed towards the internet)

  THIS COSTS REAL MONEY WHILE IT RUNS.
  $tgw_count Transit Gateways, 3 VPC attachments, 1 peering attachment,
  $eni_count Atlas endpoint ENIs, 3 SSM interface endpoints, 1 EC2 instance,
  $nat_cost_line
  plus per-GB Transit Gateway data processing and inter-region transfer.
  Run ./teardown.sh when you are done.

SUMMARY

if [ "${AUTO_APPROVE:-false}" != "true" ]; then
  read -r -p "Type the name prefix ($NAME_PREFIX) to continue: " confirm
  if [ "$confirm" != "$NAME_PREFIX" ]; then
    echo "Name prefix did not match. Aborting."
    exit 1
  fi
fi

# ── Deploy ─────────────────────────────────────────────────────────────────────

terraform -chdir=terraform init -upgrade
terraform -chdir=terraform validate
terraform -chdir=terraform apply -auto-approve

cat <<'NEXT'

Next:

  1. Give each interface endpoint ID to the matching Atlas private endpoint,
     in the same Atlas project and region, and wait for Atlas to report the
     endpoint as AVAILABLE:

       terraform -chdir=terraform output atlas_interface_endpoints

  2. Open a shell on the test VM:

       eval "$(terraform -chdir=terraform output -raw start_session_command)"

  3. On the VM, prove the network path, then run the per-region queries:

       sudo atlas-plink-test      # TCP reachability, both regions
       atlas-plink-query          # explicit reads from a secondary in each
                                  # region; prompts for the private-endpoint
                                  # URI and the password, stores neither
       atlas-plink-egress-check   # shows MongoDB ports cannot reach the
                                  # internet, only the hub VPCs

  4. Once mongosh is installed, drop the NAT gateway if you want the strictest
     posture for the demo:

       CLIENT_INTERNET_EGRESS=false ./deploy.sh

NEXT
