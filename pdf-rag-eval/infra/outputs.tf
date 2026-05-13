output "storage_account_name" {
  description = "Storage account name."
  value       = azurerm_storage_account.this.name
}

output "blob_endpoint" {
  description = "Primary blob service endpoint URL."
  value       = azurerm_storage_account.this.primary_blob_endpoint
}

output "container_name" {
  description = "Blob container that holds the PDFs."
  value       = azurerm_storage_container.pdfs.name
}

# Sensitive: account key. Retrieve with
#   terraform output -raw primary_access_key
output "primary_access_key" {
  description = "Primary access key for the storage account. Sensitive."
  sensitive   = true
  value       = azurerm_storage_account.this.primary_access_key
}

# Sensitive: full SAS-style connection string. Retrieve with
#   terraform output -raw connection_string
output "connection_string" {
  description = "DefaultEndpointsProtocol=https;... connection string. Sensitive."
  sensitive   = true
  value       = azurerm_storage_account.this.primary_connection_string
}

output "connection_string_template" {
  description = "Connection string template with the key redacted, safe to paste."
  value       = "DefaultEndpointsProtocol=https;AccountName=${azurerm_storage_account.this.name};AccountKey=<PRIMARY_KEY>;EndpointSuffix=core.windows.net"
}
