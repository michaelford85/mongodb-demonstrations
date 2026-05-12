# Resource group is owned by Terraform so `terraform destroy` is a clean
# single-shot teardown of everything created here.
resource "azurerm_resource_group" "this" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    Project   = "mongodb-demonstrations"
    Component = "cosmosdb-cluster-provisioning"
    ManagedBy = "Terraform"
  }
}

# Cosmos DB account.
#
# - `EnableNoSQLVectorSearch` capability is what activates the DiskANN /
#   quantizedFlat / flat vector index types on this account.
# - The `ip_range_filter` value is the IP allow-list for the account's data
#   plane; it is the Cosmos equivalent of the security group in the postgres
#   demo. Cosmos accepts a comma-separated list of IPs and CIDRs.
resource "azurerm_cosmosdb_account" "this" {
  name                = var.account_name
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  capabilities {
    name = "EnableNoSQLVectorSearch"
  }

  consistency_policy {
    consistency_level = var.consistency_level
  }

  geo_location {
    location          = azurerm_resource_group.this.location
    failover_priority = 0
  }

  # azurerm v4 takes a set(string) of individual IPs/CIDRs (no longer the
  # legacy comma-separated string). Cosmos itself still stores them as CSV
  # under the hood.
  ip_range_filter                   = toset(var.allowed_ip_addresses)
  public_network_access_enabled     = true
  is_virtual_network_filter_enabled = false
}

resource "azurerm_cosmosdb_sql_database" "this" {
  name                = var.database_name
  resource_group_name = azurerm_resource_group.this.name
  account_name        = azurerm_cosmosdb_account.this.name
}

# Container created with the base indexing policy only. The vector embedding
# policy and vector index are layered on by the azapi_update_resource below,
# because the azurerm provider does not yet model those fields. The vector
# path is excluded from the general index here so it does not get double-
# indexed when the vector index is added.
resource "azurerm_cosmosdb_sql_container" "this" {
  name                = var.container_name
  resource_group_name = azurerm_resource_group.this.name
  account_name        = azurerm_cosmosdb_account.this.name
  database_name       = azurerm_cosmosdb_sql_database.this.name
  partition_key_paths = [var.partition_key_path]

  autoscale_settings {
    max_throughput = var.autoscale_max_throughput
  }

  indexing_policy {
    indexing_mode = "consistent"

    included_path {
      path = "/*"
    }

    excluded_path {
      path = "${var.vector_path}/*"
    }

    excluded_path {
      path = "/_etag/?"
    }
  }
}

# Layer the vector embedding policy and vector index onto the container.
#
# Cosmos DB requires the vector policy to be set at container creation time
# and forbids modification once the container holds data, so this update
# must run on an empty container immediately after `azurerm_cosmosdb_sql_
# container.this` is created. Terraform's resource graph guarantees ordering
# via parent_id.
#
# The body merges the embedding policy with a full re-statement of the
# indexing policy (Cosmos requires the indexing policy to be re-sent in full
# when changing it). The fields here mirror what azurerm wrote, plus the
# vectorIndexes entry that azurerm cannot express.
resource "azapi_update_resource" "vector_policy" {
  type        = "Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15"
  resource_id = azurerm_cosmosdb_sql_container.this.id

  body = {
    properties = {
      resource = {
        id = var.container_name

        partitionKey = {
          paths = [var.partition_key_path]
          kind  = "Hash"
        }

        vectorEmbeddingPolicy = {
          vectorEmbeddings = [{
            path             = var.vector_path
            dataType         = "float32"
            distanceFunction = var.vector_distance_function
            dimensions       = var.vector_dimensions
          }]
        }

        indexingPolicy = {
          indexingMode = "consistent"
          automatic    = true
          includedPaths = [{
            path = "/*"
          }]
          excludedPaths = [
            { path = "${var.vector_path}/*" },
            { path = "/_etag/?" },
          ]
          vectorIndexes = [{
            path = var.vector_path
            type = var.vector_index_type
          }]
        }
      }
    }
  }
}
