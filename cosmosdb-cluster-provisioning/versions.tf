terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.20"
    }
    # azapi is required because the azurerm provider does not yet expose
    # vector_embedding_policy / vectorIndexes on Cosmos SQL containers
    # (hashicorp/terraform-provider-azurerm#29597). We layer those properties
    # on with azapi_update_resource immediately after the container is
    # created by azurerm.
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.0"
    }
  }
}
