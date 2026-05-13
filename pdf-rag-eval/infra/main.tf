resource "azurerm_resource_group" "this" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    Project   = "mongodb-demonstrations"
    Component = "pdf-rag-eval"
    ManagedBy = "Terraform"
  }
}

# Standard general-purpose v2 account, LRS replication — cheapest option that
# still supports blob versioning and SAS tokens. The IP allow-list is the
# network boundary; identical philosophy to the Cosmos demo's ip_range_filter.
resource "azurerm_storage_account" "this" {
  name                          = var.storage_account_name
  resource_group_name           = azurerm_resource_group.this.name
  location                      = azurerm_resource_group.this.location
  account_tier                  = "Standard"
  account_replication_type      = "LRS"
  account_kind                  = "StorageV2"
  min_tls_version               = "TLS1_2"
  public_network_access_enabled = true
  # Disable shared-key access? We leave it enabled because the demo scripts
  # authenticate with the account key for simplicity, mirroring the Cosmos
  # primary_key pattern. Production would prefer AAD + RBAC.
  shared_access_key_enabled = true

  network_rules {
    default_action = "Deny"
    ip_rules       = var.allowed_ip_addresses
    bypass         = ["AzureServices"]
  }

  blob_properties {
    # 7-day soft delete on blobs gives recovery headroom while the demo is
    # being iterated on. Containers also get 7-day soft delete below.
    delete_retention_policy {
      days = 7
    }
    container_delete_retention_policy {
      days = 7
    }
  }
}

resource "azurerm_storage_container" "pdfs" {
  name                  = var.container_name
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}
