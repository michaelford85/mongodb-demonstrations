output "account_name" {
  description = "Cosmos DB account name."
  value       = azurerm_cosmosdb_account.this.name
}

output "endpoint" {
  description = "Data-plane endpoint URI for the account."
  value       = azurerm_cosmosdb_account.this.endpoint
}

output "database_name" {
  description = "SQL database created in the account."
  value       = azurerm_cosmosdb_sql_database.this.name
}

output "container_name" {
  description = "SQL container with the vector policy applied."
  value       = azurerm_cosmosdb_sql_container.this.name
}

output "partition_key_path" {
  description = "Partition key path on the container."
  value       = var.partition_key_path
}

output "vector_path" {
  description = "Document path that holds the embedding vector."
  value       = var.vector_path
}

output "vector_dimensions" {
  description = "Embedding dimensionality enforced by the vector policy."
  value       = var.vector_dimensions
}

output "vector_index_type" {
  description = "Vector index type configured on the container."
  value       = var.vector_index_type
}

# Sensitive: account key. Retrieve with `terraform output -raw primary_key`.
# Mirrors how postgres-cluster-provisioning exposes db_admin_password.
output "primary_key" {
  description = "Primary master key for the Cosmos account. Sensitive."
  sensitive   = true
  value       = azurerm_cosmosdb_account.this.primary_key
}

output "primary_readonly_key" {
  description = "Primary read-only key. Useful for query-only clients in the comparison demos."
  sensitive   = true
  value       = azurerm_cosmosdb_account.this.primary_readonly_key
}

# Sensitive: full SQL API connection string including the primary key.
# Retrieve with `terraform output -raw connection_string`.
output "connection_string" {
  description = "AccountEndpoint=...;AccountKey=...; connection string. Sensitive."
  sensitive   = true
  value       = "AccountEndpoint=${azurerm_cosmosdb_account.this.endpoint};AccountKey=${azurerm_cosmosdb_account.this.primary_key};"
}

output "connection_string_template" {
  description = "Connection string with the key redacted, safe to paste into tickets or chat."
  value       = "AccountEndpoint=${azurerm_cosmosdb_account.this.endpoint};AccountKey=<PRIMARY_KEY>;"
}
