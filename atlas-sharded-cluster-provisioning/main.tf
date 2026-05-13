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
  # Effective Compute Auto-Scale ceiling. Empty input pins max = current tier
  # so the feature is enabled without actually scaling — the configuration
  # Atlas Automated Embedding (autoEmbed) requires.
  effective_compute_max = var.cluster_compute_max_instance_size != "" ? var.cluster_compute_max_instance_size : var.cluster_instance_size
}

# ── Sharded Cluster ────────────────────────────────────────────────────────────
# Uses the advanced_cluster resource (recommended over the legacy cluster resource).
# Each replication_specs block represents one shard. This is the new sharding
# schema introduced in Atlas provider 1.18 — it replaces the deprecated
# num_shards attribute.
#
# cluster_type:
#   SHARDED    — all shards share a single zone. Atlas requires every shard
#                in that zone to have the same region topology.
#   GEOSHARDED — each shard is placed in its own zone (Zone 1, Zone 2, …),
#                so shards may live in different regions. Required when
#                cluster_shards entries differ in their region_configs.

resource "mongodbatlas_advanced_cluster" "demo" {
  project_id             = var.atlas_project_id
  name                   = var.cluster_name
  cluster_type           = var.cluster_type
  mongo_db_major_version = var.mongodb_version

  dynamic "replication_specs" {
    for_each = var.cluster_shards
    content {
      # For GEOSHARDED, each shard gets its own zone so its region topology
      # is independent. For SHARDED, leave zone_name null and let Atlas put
      # every shard in the default zone.
      zone_name = var.cluster_type == "GEOSHARDED" ? "Zone ${replication_specs.key + 1}" : null

      dynamic "region_configs" {
        for_each = replication_specs.value.region_configs
        content {
          provider_name = var.cluster_cloud_provider
          region_name   = region_configs.value.region_name
          priority      = region_configs.value.priority

          electable_specs {
            instance_size = var.cluster_instance_size
            node_count    = region_configs.value.electable_nodes
          }

          # Compute Auto-Scale is a prerequisite for Atlas Automated Embedding.
          # With min == max == current tier the feature is enabled without
          # actually scaling. Override cluster_compute_max_instance_size to
          # raise the ceiling.
          dynamic "auto_scaling" {
            for_each = var.cluster_compute_autoscale_enabled ? [1] : []
            content {
              disk_gb_enabled            = true
              compute_enabled            = true
              compute_scale_down_enabled = false
              compute_min_instance_size  = var.cluster_instance_size
              compute_max_instance_size  = local.effective_compute_max
            }
          }
        }
      }
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
