provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "mongodb-demonstrations"
      Component = "postgres-cluster-provisioning"
      ManagedBy = "Terraform"
    }
  }
}
