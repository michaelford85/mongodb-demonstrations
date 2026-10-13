#!/usr/bin/env bash
# Who am I, what organization is this, and which member accounts can I assume into?
set -uo pipefail
PROFILE_ARG=""
[ -n "${1:-}" ] && PROFILE_ARG="--profile $1"

me=$(aws sts get-caller-identity $PROFILE_ARG --query Account --output text) || exit 1
mgmt=$(aws organizations describe-organization $PROFILE_ARG --query Organization.MasterAccountId --output text 2>/dev/null)
orgid=$(aws organizations describe-organization $PROFILE_ARG --query Organization.Id --output text 2>/dev/null)

echo "organization : ${orgid:-<none / no access>}"
echo "management   : ...${mgmt: -4}"
echo "you are in   : ...${me: -4} $([ "$me" = "$mgmt" ] && echo '(the management account)')"
echo
printf '%-22s %-8s %-9s %s\n' "ACCOUNT" "ID" "JOINED" "USABLE AS A SPOKE?"
aws organizations list-accounts $PROFILE_ARG --output json 2>/dev/null |
  jq -r '.Accounts[] | [.Name, .Id, .JoinedMethod] | @tsv' |
  while IFS=$'\t' read -r name id joined; do
    if [ "$id" = "$mgmt" ]; then
      verdict="no - this is the hub/management account"
    elif aws sts assume-role $PROFILE_ARG \
        --role-arn "arn:aws:iam::${id}:role/OrganizationAccountAccessRole" \
        --role-session-name org-report --duration-seconds 900 >/dev/null 2>&1; then
      verdict="YES - OrganizationAccountAccessRole assumable"
    else
      verdict="no - cannot assume OrganizationAccountAccessRole"
    fi
    printf '%-22s ...%-5s %-9s %s\n' "$name" "${id: -4}" "$joined" "$verdict"
  done
