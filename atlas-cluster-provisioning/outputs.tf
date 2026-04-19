output "project_id" {
  description = "Atlas project ID (the existing project resources were deployed into)"
  value       = var.atlas_project_id
}

output "cluster_id" {
  description = "Atlas cluster ID"
  value       = mongodbatlas_advanced_cluster.demo.cluster_id
}

output "mongodb_version" {
  description = "MongoDB version running on the cluster"
  value       = mongodbatlas_advanced_cluster.demo.mongo_db_version
}

output "connection_strings" {
  description = "Standard and SRV connection strings for the cluster"
  value = {
    standard     = mongodbatlas_advanced_cluster.demo.connection_strings[0].standard
    standard_srv = mongodbatlas_advanced_cluster.demo.connection_strings[0].standard_srv
  }
}

output "state_name" {
  description = "Current state of the cluster (IDLE = ready)"
  value       = mongodbatlas_advanced_cluster.demo.state_name
}
