variable "aws_region" {
  type        = string
  description = "AWS region in which to create the cluster."
  default     = "us-east-1"
}

variable "cluster_identifier" {
  type        = string
  description = "Aurora cluster identifier. Lowercase, alphanumeric and hyphens."
  default     = "pgvector-demo"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,62}$", var.cluster_identifier))
    error_message = "Must start with a letter, be lowercase, contain only letters/digits/hyphens, and be 63 chars or fewer."
  }
}

variable "db_name" {
  type        = string
  description = "Initial database name created inside the cluster."
  default     = "appdb"
}

variable "db_admin_username" {
  type        = string
  description = "Master username for the Aurora cluster."
  sensitive   = false

  validation {
    condition     = !contains(["rdsadmin", "admin"], lower(var.db_admin_username)) && length(var.db_admin_username) >= 4
    error_message = "Pick a non-reserved username (avoid rdsadmin/admin) of at least 4 characters."
  }
}

variable "db_admin_password" {
  type        = string
  description = "Master password for the Aurora cluster. 16+ characters recommended."
  sensitive   = true

  validation {
    condition     = length(var.db_admin_password) >= 16
    error_message = "Password must be at least 16 characters."
  }
}

variable "engine_version" {
  type        = string
  description = "Aurora PostgreSQL engine version. Use 15.3+ for pgvector support."
  default     = "16.4"
}

variable "instance_class" {
  type        = string
  description = "DB instance class for the cluster instance."
  default     = "db.t4g.medium"
}

variable "publicly_accessible" {
  type        = bool
  description = "Whether the cluster instance has a public endpoint. Demo default is true so a developer laptop can reach it."
  default     = true
}

variable "allowed_cidr_blocks" {
  type        = list(string)
  description = "CIDR blocks permitted to connect to the cluster on TCP 5432. MUST be set explicitly; do not leave open to the world."

  validation {
    condition     = length(var.allowed_cidr_blocks) > 0
    error_message = "Provide at least one CIDR block (e.g. your public IP as a /32)."
  }

  validation {
    condition     = !contains(var.allowed_cidr_blocks, "0.0.0.0/0")
    error_message = "Refusing to open the cluster to 0.0.0.0/0. Restrict to your own IP range."
  }
}

variable "backup_retention_days" {
  type        = number
  description = "Days of automated backups to retain. 1 keeps cost low for demos."
  default     = 1
}
