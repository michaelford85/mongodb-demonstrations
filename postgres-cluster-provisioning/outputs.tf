output "cluster_endpoint" {
  description = "Writer endpoint for the Aurora cluster."
  value       = aws_rds_cluster.this.endpoint
}

output "reader_endpoint" {
  description = "Reader endpoint for the Aurora cluster."
  value       = aws_rds_cluster.this.reader_endpoint
}

output "port" {
  description = "TCP port the cluster listens on."
  value       = aws_rds_cluster.this.port
}

output "database_name" {
  description = "Initial database created in the cluster."
  value       = aws_rds_cluster.this.database_name
}

output "master_username" {
  description = "Master DB username."
  value       = aws_rds_cluster.this.master_username
}

output "psql_command" {
  description = "psql command to open a shell against the writer endpoint. Prompts for password."
  value = format(
    "psql -h %s -p %d -U %s -d %s",
    aws_rds_cluster.this.endpoint,
    aws_rds_cluster.this.port,
    aws_rds_cluster.this.master_username,
    aws_rds_cluster.this.database_name,
  )
}

# Sensitive output: contains the password. Retrieve with
#   terraform output -raw connection_string
# Terraform redacts this value from human-readable plan/apply logs.
output "connection_string" {
  description = "Full libpq URI including the master password. Sensitive."
  sensitive   = true
  value = format(
    "postgresql://%s:%s@%s:%d/%s",
    aws_rds_cluster.this.master_username,
    var.db_admin_password,
    aws_rds_cluster.this.endpoint,
    aws_rds_cluster.this.port,
    aws_rds_cluster.this.database_name,
  )
}

output "connection_string_template" {
  description = "Connection string template with the password redacted, safe to paste into tickets or chat."
  value = format(
    "postgresql://%s:<PASSWORD>@%s:%d/%s",
    aws_rds_cluster.this.master_username,
    aws_rds_cluster.this.endpoint,
    aws_rds_cluster.this.port,
    aws_rds_cluster.this.database_name,
  )
}
