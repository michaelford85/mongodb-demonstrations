variable "atlas_public_key" {
  description = "MongoDB Atlas API public key"
  type        = string
  sensitive   = true
}

variable "atlas_private_key" {
  description = "MongoDB Atlas API private key"
  type        = string
  sensitive   = true
}

variable "atlas_project_id" {
  description = "ID of the existing Atlas project to deploy into"
  type        = string
}

variable "cluster_name" {
  description = "Name of the Atlas cluster"
  type        = string
}

variable "cluster_type" {
  description = "SHARDED (all shards share one zone — all shards must have identical region topology) or GEOSHARDED (each shard goes in its own zone — shards may be in different regions)."
  type        = string
  default     = "SHARDED"
  validation {
    condition     = contains(["SHARDED", "GEOSHARDED"], var.cluster_type)
    error_message = "cluster_type must be SHARDED or GEOSHARDED."
  }
}

variable "cluster_cloud_provider" {
  description = "Cloud provider for the cluster (AWS, GCP, or AZURE)"
  type        = string
  validation {
    condition     = contains(["AWS", "GCP", "AZURE"], var.cluster_cloud_provider)
    error_message = "cluster_cloud_provider must be one of: AWS, GCP, AZURE"
  }
}

variable "cluster_instance_size" {
  description = "Atlas cluster instance size (e.g. M10, M30, M40). An explicit _NVME suffix (e.g. M40_NVME) selects local NVMe storage regardless of cluster_storage_class."
  type        = string
  default     = "M30"
  validation {
    condition     = can(regex("^M[0-9]+(_NVME)?$", upper(var.cluster_instance_size)))
    error_message = "cluster_instance_size must look like M30 or M40_NVME."
  }
}

variable "cluster_storage_class" {
  description = "Storage class for the cluster: SSD (network-attached, the Atlas default) or NVME (local NVMe SSD). NVME applies the _NVME suffix to the instance size — available on AWS (M40+) and AZURE (M60+) only, and not on GCP."
  type        = string
  default     = "SSD"
  validation {
    condition     = contains(["SSD", "NVME"], upper(var.cluster_storage_class))
    error_message = "cluster_storage_class must be SSD or NVME."
  }
}

variable "cluster_disk_size_gb" {
  description = "Root volume capacity in GB. 0 (default) lets Atlas apply the default size for the tier. Must be 0 for local NVMe clusters, where disk capacity is fixed by the tier."
  type        = number
  default     = 0
  validation {
    condition     = var.cluster_disk_size_gb == 0 || (var.cluster_disk_size_gb >= 10 && var.cluster_disk_size_gb <= 4096)
    error_message = "cluster_disk_size_gb must be 0 (Atlas default) or between 10 and 4096."
  }
}

variable "cluster_backup_enabled" {
  description = "Enable Atlas Cloud Backup. Forced on for local NVMe clusters, which Atlas refuses to create without it."
  type        = bool
  default     = false
}

variable "mongodb_version" {
  description = "MongoDB major version (e.g. 7.0, 8.0)"
  type        = string
  default     = "8.0"
}

variable "cluster_shards" {
  description = "List of shard config objects. Each shard contains its own region_configs (region_name, electable_nodes, priority). With cluster_type=GEOSHARDED every shard lands in its own zone so the region topologies may differ; with cluster_type=SHARDED Atlas requires every shard's region topology to match."
  type = list(object({
    region_configs = list(object({
      region_name     = string
      electable_nodes = number
      priority        = number
    }))
  }))
  validation {
    condition     = length(var.cluster_shards) >= 1
    error_message = "cluster_shards must contain at least one shard."
  }
}

variable "cluster_search_nodes" {
  description = "Number of dedicated Atlas Search nodes (0 = shared search on electable nodes)"
  type        = number
  default     = 0
}

variable "cluster_compute_autoscale_enabled" {
  description = "Enable Atlas Compute Auto-Scale. Required for Atlas Automated Embedding (autoEmbed vector search indexes)."
  type        = bool
  default     = true
}

variable "cluster_compute_max_instance_size" {
  description = "Ceiling for Compute Auto-Scale. Empty string (default) pins max = cluster_instance_size, enabling the feature without actually scaling."
  type        = string
  default     = ""
}

variable "db_admin_user" {
  description = "Username for the Atlas admin database user"
  type        = string
  default     = "admin"
}

variable "db_admin_password" {
  description = "Password for the Atlas admin database user"
  type        = string
  sensitive   = true
}

variable "db_app_user" {
  description = "Username for the application database user (readWriteAnyDatabase)"
  type        = string
  default     = "app-user"
}

variable "db_app_password" {
  description = "Password for the application database user"
  type        = string
  sensitive   = true
}

variable "db_monitor_user" {
  description = "Username for the monitoring database user (clusterMonitor)"
  type        = string
  default     = "monitor-user"
}

variable "db_monitor_password" {
  description = "Password for the monitoring database user"
  type        = string
  sensitive   = true
}
