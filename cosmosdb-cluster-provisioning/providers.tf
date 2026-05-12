provider "azurerm" {
  features {}

  # Subscription is read from ARM_SUBSCRIPTION_ID (set in .env). Auth itself
  # is expected to come from `az login` on the host running terraform.
}

provider "azapi" {
  # Inherits credentials from the Azure CLI session, same as azurerm.
}
