terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.5"
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

locals {
  # Regional Spanner instance config name, e.g. regional-us-central1.
  # For multi-region configs (nam3, eur3, nam-eur-asia1, …) override this
  # local with the desired config string.
  spanner_config = "regional-${var.gcp_region}"

  # Service account ID must be 6-30 chars, [a-z][-a-z0-9]*[a-z0-9].
  # Spanner instance IDs already conform; we just bound the length.
  harness_sa_id = format("sp-%s-sa", substr(var.spanner_instance_id, 0, 24))
}

# ── Spanner Instance ──────────────────────────────────────────────────────────

resource "google_spanner_instance" "demo" {
  name             = var.spanner_instance_id
  config           = local.spanner_config
  display_name     = var.spanner_instance_id
  processing_units = var.spanner_processing_units
}

# ── Spanner Database ──────────────────────────────────────────────────────────

resource "google_spanner_database" "demo" {
  instance         = google_spanner_instance.demo.name
  name             = var.spanner_database_id
  database_dialect = var.spanner_dialect

  # Let teardown.sh destroy the database without manual unprotection.
  deletion_protection = false
}

# ── Harness Service Account ───────────────────────────────────────────────────
# Identity the demo harness uses to talk to Spanner. Created here so it is
# scoped to this deployment and torn down with it.

resource "google_service_account" "harness" {
  account_id   = local.harness_sa_id
  display_name = "Spanner harness SA for ${var.spanner_instance_id}"
}

resource "google_spanner_instance_iam_member" "harness" {
  instance = google_spanner_instance.demo.name
  role     = "roles/spanner.databaseUser"
  member   = "serviceAccount:${google_service_account.harness.email}"
}

resource "google_service_account_key" "harness" {
  service_account_id = google_service_account.harness.name
}
