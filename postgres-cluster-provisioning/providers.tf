provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "mongodb-demonstrations"
      Component = "postgres-cluster-provisioning"
      ManagedBy = "Terraform"
    }
  }
}

# Connects to the cluster we just created to declaratively manage in-database
# objects (currently just the `vector` extension). The machine running
# terraform must have its public IP listed in `allowed_cidr_blocks`.
#
# `superuser = false` is required for RDS / Aurora: the master role is
# `rds_superuser`, not a true Postgres superuser, and the provider will try
# privileged operations otherwise.
provider "postgresql" {
  host            = aws_rds_cluster.this.endpoint
  port            = aws_rds_cluster.this.port
  database        = aws_rds_cluster.this.database_name
  username        = aws_rds_cluster.this.master_username
  password        = var.db_admin_password
  sslmode         = "require"
  superuser       = false
  connect_timeout = 60
}
