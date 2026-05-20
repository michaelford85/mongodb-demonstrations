output "project_id" {
  description = "GCP project ID resources were deployed into"
  value       = var.gcp_project_id
}

output "instance_id" {
  description = "Spanner instance ID"
  value       = google_spanner_instance.demo.name
}

output "instance_config" {
  description = "Spanner instance config (regional-<region> or multi-region name)"
  value       = google_spanner_instance.demo.config
}

output "database_id" {
  description = "Spanner database ID"
  value       = google_spanner_database.demo.name
}

output "database_dialect" {
  description = "Database dialect (GOOGLE_STANDARD_SQL or POSTGRESQL)"
  value       = google_spanner_database.demo.database_dialect
}

output "database_path" {
  description = "Fully-qualified Spanner database resource path"
  value       = "projects/${var.gcp_project_id}/instances/${google_spanner_instance.demo.name}/databases/${google_spanner_database.demo.name}"
}

output "harness_service_account_email" {
  description = "Email of the service account the harness should authenticate as"
  value       = google_service_account.harness.email
}

output "harness_service_account_key" {
  description = "Base64-encoded JSON private key for the harness service account. Decode (base64 -d) to obtain the JSON key file."
  value       = google_service_account_key.harness.private_key
  sensitive   = true
}
