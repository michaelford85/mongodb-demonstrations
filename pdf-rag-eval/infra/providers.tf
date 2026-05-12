provider "azurerm" {
  features {
    resource_group {
      # Allow `terraform destroy` to remove the RG even if there are
      # ephemeral diagnostic resources Cosmos / Storage left behind.
      prevent_deletion_if_contains_resources = false
    }
  }
}
