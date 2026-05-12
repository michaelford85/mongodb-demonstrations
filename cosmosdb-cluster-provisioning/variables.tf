variable "location" {
  type        = string
  description = "Azure region in which to create the Cosmos DB account."
  default     = "eastus"
}

variable "resource_group_name" {
  type        = string
  description = "Name of the resource group Terraform will create and own. Destroyed by teardown.sh."
  default     = "cosmos-vector-demo-rg"
}

variable "account_name" {
  type        = string
  description = "Cosmos DB account name. Must be globally unique, 3-44 chars, lowercase letters/digits/hyphens."

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,42}[a-z0-9]$", var.account_name))
    error_message = "Account name must be 3-44 chars, lowercase letters/digits/hyphens, starting and ending alphanumeric."
  }
}

variable "database_name" {
  type        = string
  description = "Cosmos SQL database name."
  default     = "ragdb"
}

variable "container_name" {
  type        = string
  description = "Cosmos SQL container name."
  default     = "chunks"
}

variable "partition_key_path" {
  type        = string
  description = "Partition key path. /document_id puts one logical partition per source PDF, which makes the 20 GB / 10K RU/s logical-partition ceiling easy to demonstrate."
  default     = "/document_id"
}

variable "vector_path" {
  type        = string
  description = "Document path that holds the embedding vector. Must be excluded from the general indexing policy so it only lives in the vector index."
  default     = "/embedding"
}

variable "vector_dimensions" {
  type        = number
  description = "Embedding dimensionality. 1024 matches voyage-4-large's default output."
  default     = 1024

  validation {
    condition     = var.vector_dimensions > 0 && var.vector_dimensions <= 4096
    error_message = "DiskANN supports up to 4096 dimensions on Cosmos DB for NoSQL."
  }
}

variable "vector_distance_function" {
  type        = string
  description = "Distance function for vector similarity. cosine matches the default voyage-4-large recommendation."
  default     = "cosine"

  validation {
    condition     = contains(["cosine", "dotproduct", "euclidean"], var.vector_distance_function)
    error_message = "Must be one of cosine, dotproduct, euclidean."
  }
}

variable "vector_index_type" {
  type        = string
  description = "Vector index type. diskANN gives the lowest RU cost / latency at scale; flat and quantizedFlat are alternatives."
  default     = "diskANN"

  validation {
    condition     = contains(["flat", "quantizedFlat", "diskANN"], var.vector_index_type)
    error_message = "Must be one of flat, quantizedFlat, diskANN."
  }
}

variable "autoscale_max_throughput" {
  type        = number
  description = "Maximum autoscale RU/s for the container. Autoscale scales between 10% and 100% of this value. 1000 is the minimum Cosmos allows."
  default     = 1000

  validation {
    condition     = var.autoscale_max_throughput >= 1000 && var.autoscale_max_throughput % 1000 == 0
    error_message = "Autoscale max_throughput must be at least 1000 RU/s and a multiple of 1000."
  }
}

variable "consistency_level" {
  type        = string
  description = "Account consistency level. Session is the Cosmos default and the most common production choice."
  default     = "Session"

  validation {
    condition     = contains(["Eventual", "ConsistentPrefix", "Session", "BoundedStaleness", "Strong"], var.consistency_level)
    error_message = "Must be a valid Cosmos consistency level."
  }
}

variable "allowed_ip_addresses" {
  type        = list(string)
  description = "Public IPv4 addresses or CIDRs permitted to reach the account's data plane. MUST be set explicitly. Use your laptop's IP (curl -s https://checkip.amazonaws.com)."

  validation {
    condition     = length(var.allowed_ip_addresses) > 0
    error_message = "Provide at least one IP address (e.g. your laptop's public IP)."
  }

  validation {
    condition     = !contains(var.allowed_ip_addresses, "0.0.0.0/0")
    error_message = "Refusing to open the account to 0.0.0.0/0. Restrict to your own IPs."
  }
}
