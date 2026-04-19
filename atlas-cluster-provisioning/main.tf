terraform {
  required_providers {
    mongodbatlas = {
      source  = "mongodb/mongodbatlas"
      version = "~> 1.15"
    }
  }
  required_version = ">= 1.5"
}

provider "mongodbatlas" {
  public_key  = var.atlas_public_key
  private_key = var.atlas_private_key
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
          instance_size = var.cluster_instance_size
          node_count    = region_configs.value.electable_nodes
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
