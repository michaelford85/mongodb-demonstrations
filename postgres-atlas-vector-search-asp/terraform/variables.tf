variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "resource_prefix" {
  type    = string
  default = "pg-atlas-asp-demo"
}

# ── Network ────────────────────────────────────────────────────────────
variable "vpc_cidr" {
  type    = string
  default = "10.90.0.0/16"
}

# Optional: your local /32 so you can seed PostgreSQL over TLS.
# Leave empty to keep the database fully private (then run seeding from
# a host inside the VPC, e.g. via Client VPN or a bastion).
variable "local_ingress_cidr" {
  type    = string
  default = ""
}

# Explicit switch for internet egress/ingress via an Internet Gateway on the
# demo route table. Required (together with local_ingress_cidr and
# rds_publicly_accessible = true) for seeding PostgreSQL from a laptop.
# Keep false for a fully private stack.
variable "enable_igw" {
  type    = bool
  default = false
}

# ── Atlas VPC peering (required so Atlas Stream Processing can reach MSK) ──
# Created from the ATLAS side (Atlas UI → Network Access → Peering →
# "Add outbound connection" → AWS), pointing at this stack's demo VPC and
# its CIDR. While it sits "Waiting for Approval", copy its Peering ID
# (pcx-...) and Atlas CIDR here; Terraform accepts it and wires the AWS side.
variable "atlas_peering_id" {
  type    = string
  default = ""
}

variable "atlas_cidr" {
  type    = string
  default = ""
}

variable "atlas_owner_account_id" {
  type    = string
  default = ""
}

# ── RDS PostgreSQL source ──────────────────────────────────────────────
variable "db_name" {
  type    = string
  default = "demodb"
}

variable "db_admin_username" {
  type    = string
  default = "demo_admin"
}

# Supply via TF_VAR_db_admin_password or `-var`, never in tfvars.
variable "db_admin_password" {
  type      = string
  sensitive = true
}

variable "db_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "rds_publicly_accessible" {
  type    = bool
  default = false
}

# ── MSK ────────────────────────────────────────────────────────────────
# MSK only offers 3.8.x+ for new standard-tier clusters; AWS DMS supports
# SASL/SCRAM up to Kafka 3.8, so 3.8.x is the newest compatible version.
variable "msk_kafka_version" {
  type    = string
  default = "3.8.x"
}

variable "msk_instance_type" {
  type    = string
  default = "kafka.t3.small"
}

variable "msk_broker_count" {
  type    = number
  default = 2
}

# ── DMS ────────────────────────────────────────────────────────────────
variable "dms_instance_class" {
  type    = string
  default = "dms.t3.small"
}

variable "kafka_topic" {
  type    = string
  default = "cdc-knowledge-items"
}
