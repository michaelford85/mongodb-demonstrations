provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "mongodb-demonstrations"
      Component = "postgres-atlas-vector-search-asp"
      Purpose   = "demo"
      ManagedBy = "Terraform"
    }
  }
}
