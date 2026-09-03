variable "gcp_project_id" {
  description = "GCP project ID to deploy Spanner resources into"
  type        = string
}

variable "gcp_region" {
  description = "GCP region (drives the regional Spanner instance config)"
  type        = string
  default     = "us-central1"
}

variable "spanner_instance_id" {
  description = "Spanner instance ID (2-30 chars, [a-z][-a-z0-9]*[a-z0-9])"
  type        = string
}

variable "spanner_database_id" {
  description = "Spanner database ID (2-30 chars, [a-z][-_a-z0-9]*[a-z0-9])"
  type        = string
}

variable "spanner_processing_units" {
  description = "Spanner processing units. Minimum 100; multiples of 100 below 1000, multiples of 1000 above."
  type        = number
  default     = 100
  validation {
    condition     = var.spanner_processing_units >= 100 && var.spanner_processing_units % 100 == 0
    error_message = "spanner_processing_units must be a multiple of 100 and at least 100."
  }
}

variable "spanner_dialect" {
  description = "Spanner database dialect (GOOGLE_STANDARD_SQL or POSTGRESQL)"
  type        = string
  default     = "GOOGLE_STANDARD_SQL"
  validation {
    condition     = contains(["GOOGLE_STANDARD_SQL", "POSTGRESQL"], var.spanner_dialect)
    error_message = "spanner_dialect must be one of: GOOGLE_STANDARD_SQL, POSTGRESQL"
  }
}
