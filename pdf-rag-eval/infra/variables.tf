variable "location" {
  type        = string
  description = "Azure region. Use the same region as the Cosmos demo to keep latency low."
  default     = "eastus"
}

variable "resource_group_name" {
  type        = string
  description = "Resource group Terraform owns. Destroyed by teardown.sh."
  default     = "pdf-rag-eval-rg"
}

variable "storage_account_name" {
  type        = string
  description = "Storage account name. Globally unique, 3-24 chars, lowercase letters and digits ONLY."

  validation {
    condition     = can(regex("^[a-z0-9]{3,24}$", var.storage_account_name))
    error_message = "3-24 chars, lowercase letters and digits only (no hyphens, no uppercase)."
  }
}

variable "container_name" {
  type        = string
  description = "Blob container that will hold the demo PDFs."
  default     = "pdfs"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{2,62}$", var.container_name))
    error_message = "3-63 chars, lowercase letters/digits/hyphens, must start alphanumeric."
  }
}

variable "allowed_ip_addresses" {
  type        = list(string)
  description = "Public IPv4 addresses or CIDRs permitted to reach the storage account. MUST be set explicitly."

  validation {
    condition     = length(var.allowed_ip_addresses) > 0
    error_message = "Provide at least one IP address (e.g. your laptop's public IP)."
  }

  validation {
    condition     = !contains(var.allowed_ip_addresses, "0.0.0.0/0")
    error_message = "Refusing to open the account to 0.0.0.0/0. Restrict to your own IPs."
  }
}
