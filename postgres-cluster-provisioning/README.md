# Aurora PostgreSQL cluster — Terraform provisioning

This directory creates a small Amazon Aurora PostgreSQL cluster suitable for
demos that exercise `pgvector` (e.g. the sibling `multi-region-rag-eval`
project). Everything is parameterised through environment variables so no
secrets ever land in source control.

## What gets created

| Resource                       | Purpose                                              |
|--------------------------------|------------------------------------------------------|
| `aws_rds_cluster`              | Aurora PostgreSQL cluster.                           |
| `aws_rds_cluster_instance`     | A single writer instance (`db.t4g.medium` default).  |
| `aws_db_subnet_group`          | Subnet group spanning the default VPC's subnets.     |
| `aws_security_group`           | Allows TCP 5432 only from the CIDRs you allow-list.  |

The default VPC is used to keep the surface area small. The engine version
defaults to **Aurora PostgreSQL 16.4**, which supports `pgvector` as a regular
`CREATE EXTENSION vector;` install.

## Prerequisites

- **Terraform** ≥ 1.5 (`brew install terraform`).
- **AWS CLI** with working programmatic access already configured
  (`aws sts get-caller-identity` should succeed). No keys are read from
  `.env`; we only set the region there.
- An AWS account that still has its **default VPC** in the target region.
- `psql` (optional) to connect after provisioning.

> Cost note: a `db.t4g.medium` Aurora instance plus storage runs roughly
> $60–80/month if left running. Use `./teardown.sh` when you are done.

## Setup

```bash
cd postgres-cluster-provisioning

# 1. Copy the env template and fill in real values.
cp .env.example .env
$EDITOR .env
#   At minimum, set:
#     TF_VAR_db_admin_username       (avoid 'admin' / 'rdsadmin')
#     TF_VAR_db_admin_password       (16+ characters)
#     TF_VAR_allowed_cidr_blocks     (e.g. ["1.2.3.4/32"] — your IP)

# 2. Provision. setup.sh sources .env, runs terraform init + apply, and
#    prints the non-sensitive connection details.
./setup.sh
```

After `setup.sh` finishes you will see a `connection_string_template` output
of the form:

```
postgresql://appadmin:<PASSWORD>@pgvector-demo.cluster-xxxx.us-east-1.rds.amazonaws.com:5432/appdb
```

To pull the **full** connection string (including the password) into a shell
variable without echoing it, run:

```bash
export PG_CONN_STR="$(terraform output -raw connection_string)"
```

`terraform output -raw` reads the value directly from state; it is the
recommended way to consume a `sensitive = true` output. You can now hand
`$PG_CONN_STR` to any client (psql, psycopg, etc.).

### Enabling pgvector

`pgvector` ships with Aurora PostgreSQL 15.3 and newer but is not enabled by
default. Once the cluster is reachable:

```bash
psql "$PG_CONN_STR" -c 'CREATE EXTENSION IF NOT EXISTS vector;'
```

The sibling demo `multi-region-rag-eval` expects this extension to be present.

## Variables

All variables can be set via `TF_VAR_*` environment variables or
`terraform.tfvars`. The ones in `.env.example` are the ones you are most
likely to change.

| Variable                  | Default          | Notes                                                  |
|---------------------------|------------------|--------------------------------------------------------|
| `aws_region`              | `us-east-1`      | Use `AWS_REGION` env var to override at the CLI level. |
| `cluster_identifier`      | `pgvector-demo`  | Lowercase, ≤ 63 chars.                                 |
| `db_name`                 | `appdb`          | Initial database.                                      |
| `db_admin_username`       | (required)       | Must not be `admin` or `rdsadmin`.                     |
| `db_admin_password`       | (required)       | 16+ characters enforced by validation.                 |
| `engine_version`          | `16.4`           | 15.3+ supports pgvector.                               |
| `instance_class`          | `db.t4g.medium`  | Smallest available for Aurora PostgreSQL.              |
| `publicly_accessible`     | `true`           | Demo default. Flip to `false` for VPC-only access.     |
| `allowed_cidr_blocks`     | (required)       | List of CIDRs; `0.0.0.0/0` is rejected.                |
| `backup_retention_days`   | `1`              | Increase for any non-demo use.                         |

## Teardown

```bash
./teardown.sh
```

This runs `terraform destroy -auto-approve` and removes every resource the
setup created. Because `skip_final_snapshot = true`, no snapshot is taken —
appropriate for a demo cluster, **never** appropriate for production.

## Security notes

- `.env` is in `.gitignore`. Never commit it.
- The security group only opens 5432 to the CIDRs you list. The validation
  block on `allowed_cidr_blocks` refuses `0.0.0.0/0` to prevent accidental
  internet exposure of the database.
- The `connection_string` Terraform output is marked `sensitive = true`, so
  it is redacted from `terraform apply` logs. Use `terraform output -raw
  connection_string` to retrieve it programmatically.
- Storage encryption is enabled by default (`storage_encrypted = true`).
- Local Terraform state (`terraform.tfstate`) contains the master password.
  For shared use, switch to a remote backend (S3 + DynamoDB lock) and apply
  appropriate IAM controls.

## Troubleshooting

- **"no default VPC found"** — your account has had its default VPC deleted.
  Recreate it (`aws ec2 create-default-vpc`) or extend `main.tf` to point at
  an existing VPC and subnet group of your choice.
- **Connection times out** — your public IP changed. Re-check
  `curl -s https://checkip.amazonaws.com`, update `TF_VAR_allowed_cidr_blocks`
  in `.env`, and re-run `./setup.sh` to apply the security group change.
- **`InvalidParameterCombination: Cannot find version 16.4`** — Aurora
  version availability varies by region. Run
  `aws rds describe-db-engine-versions --engine aurora-postgresql --query 'DBEngineVersions[].EngineVersion' --output text`
  and set `TF_VAR_engine_version` accordingly.
