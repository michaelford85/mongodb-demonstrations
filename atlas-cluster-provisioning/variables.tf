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

variable "cluster_cloud_provider" {
  description = "Cloud provider for the cluster (AWS, GCP, or AZURE)"
  type        = string
  validation {
    condition     = contains(["AWS", "GCP", "AZURE"], var.cluster_cloud_provider)
    error_message = "cluster_cloud_provider must be one of: AWS, GCP, AZURE"
  }
}

variable "cluster_instance_size" {
  description = "Atlas cluster instance size (e.g. M10, M20, M30)"
  type        = string
  default     = "M30"
}

variable "mongodb_version" {
  description = "MongoDB major version (e.g. 7.0, 8.0)"
  type        = string
  default     = "8.0"
}

variable "cluster_regions" {
  description = "List of region config objects. Each object: region_name, electable_nodes, priority."
  type = list(object({
    region_name     = string
    electable_nodes = number
    priority        = number
  }))
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
