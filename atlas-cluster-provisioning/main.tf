terraform {
  required_providers {
    mongodbatlas = {
      source  = "mongodb/mongodbatlas"
      version = "~> 1.18"
    }
  }
  required_version = ">= 1.5"
}

provider "mongodbatlas" {
  public_key  = var.atlas_public_key
  private_key = var.atlas_private_key
}

locals {
  # ── Storage class ────────────────────────────────────────────────────────────
  # Atlas selects local NVMe storage through the instance-size suffix, e.g.
  # M40_NVME. Local NVMe is picked either by setting cluster_storage_class to
  # NVME or by naming an already-suffixed tier in cluster_instance_size.
  storage_class = upper(var.cluster_storage_class)
  use_nvme      = local.storage_class == "NVME" || endswith(upper(var.cluster_instance_size), "_NVME")
  nvme_suffix   = local.use_nvme ? "_NVME" : ""

  # Strip any suffix the operator typed, then re-apply it from the storage
  # class so both inputs always agree on one tier name.
  instance_size_base = replace(upper(var.cluster_instance_size), "_NVME", "")
  compute_max_base   = var.cluster_compute_max_instance_size != "" ? replace(upper(var.cluster_compute_max_instance_size), "_NVME", "") : local.instance_size_base

  effective_instance_size = "${local.instance_size_base}${local.nvme_suffix}"

  # Effective Compute Auto-Scale ceiling. Empty input pins max = current tier
  # so the feature is enabled without actually scaling — the configuration
  # Atlas Automated Embedding (autoEmbed) requires.
  effective_compute_max = "${local.compute_max_base}${local.nvme_suffix}"

  # NVMe disk size is fixed by the tier and Atlas rejects an explicit value.
  # 0 means "let Atlas apply the default for the tier".
  effective_disk_size_gb = local.use_nvme || var.cluster_disk_size_gb == 0 ? null : var.cluster_disk_size_gb

  # Cluster-tier and disk auto-scaling are unavailable on the Local NVMe SSD
  # class, so the auto_scaling block is dropped entirely for NVMe clusters.
  compute_autoscale_enabled = var.cluster_compute_autoscale_enabled && !local.use_nvme
}

# ── Cluster ────────────────────────────────────────────────────────────────────
# Uses the advanced_cluster resource (recommended over the legacy cluster resource).
# replication_specs.region_configs drives multi-region topology.

resource "mongodbatlas_advanced_cluster" "demo" {
  project_id             = var.atlas_project_id
  name                   = var.cluster_name
  cluster_type           = "REPLICASET"
  mongo_db_major_version = var.mongodb_version

  replication_specs {
    dynamic "region_configs" {
      for_each = var.cluster_regions
      content {
        provider_name = var.cluster_cloud_provider
        region_name   = region_configs.value.region_name
        priority      = region_configs.value.priority

        electable_specs {
          instance_size = local.effective_instance_size
          node_count    = region_configs.value.electable_nodes
          disk_size_gb  = local.effective_disk_size_gb
        }

        # Compute Auto-Scale is a prerequisite for Atlas Automated Embedding.
        # With min == max == current tier the feature is enabled without
        # actually scaling. Override cluster_compute_max_instance_size to
        # raise the ceiling. Skipped entirely for local NVMe clusters, which
        # Atlas does not auto-scale.
        dynamic "auto_scaling" {
          for_each = local.compute_autoscale_enabled ? [1] : []
          content {
            disk_gb_enabled            = true
            compute_enabled            = true
            compute_scale_down_enabled = false
            compute_min_instance_size  = local.effective_instance_size
            compute_max_instance_size  = local.effective_compute_max
          }
        }
      }
    }
  }

  lifecycle {
    precondition {
      condition     = !local.use_nvme || contains(["AWS", "AZURE"], var.cluster_cloud_provider)
      error_message = "Local NVMe storage is only offered on AWS and AZURE. Use cluster_storage_class = SSD, or change cluster_cloud_provider."
    }

    precondition {
      condition     = !local.use_nvme || var.cluster_disk_size_gb == 0
      error_message = "cluster_disk_size_gb must be 0 with local NVMe storage — Atlas fixes disk capacity per NVMe tier and rejects an explicit disk size."
    }
  }
}

# ── Dedicated Search Nodes (optional) ─────────────────────────────────────────
# Only provisioned when CLUSTER_SEARCH_NODES > 0.

resource "mongodbatlas_search_deployment" "demo" {
  count        = var.cluster_search_nodes > 0 ? 1 : 0
  project_id   = var.atlas_project_id
  cluster_name = mongodbatlas_advanced_cluster.demo.name

  specs = [
    {
      instance_size = "S20_HIGHCPU_NVME"
      node_count    = var.cluster_search_nodes
    }
  ]
}

# ── Admin Database User ────────────────────────────────────────────────────────

resource "mongodbatlas_database_user" "admin" {
  project_id         = var.atlas_project_id
  username           = var.db_admin_user
  password           = var.db_admin_password
  auth_database_name = "admin"

  roles {
    role_name     = "atlasAdmin"
    database_name = "admin"
  }
}

# ── Application Database User ──────────────────────────────────────────────────
# Read/write on every database, with no administrative privileges.

resource "mongodbatlas_database_user" "app" {
  project_id         = var.atlas_project_id
  username           = var.db_app_user
  password           = var.db_app_password
  auth_database_name = "admin"

  roles {
    role_name     = "readWriteAnyDatabase"
    database_name = "admin"
  }
}

# ── Monitoring Database User ───────────────────────────────────────────────────
# Read-only access to server status and diagnostic commands. No data access.

resource "mongodbatlas_database_user" "monitor" {
  project_id         = var.atlas_project_id
  username           = var.db_monitor_user
  password           = var.db_monitor_password
  auth_database_name = "admin"

  roles {
    role_name     = "clusterMonitor"
    database_name = "admin"
  }
}
