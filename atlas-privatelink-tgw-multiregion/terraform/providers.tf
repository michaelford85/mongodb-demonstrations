# One aliased AWS provider per lab region.
#
# Terraform cannot generate provider configurations dynamically, so every
# region this lab spans needs its own alias here. Everything downstream of the
# provider (variables, validation, modules, outputs) is keyed by the same
# region key, so adding a third region is an additive change:
#
#   1. add a "c" entry to the `hubs` variable (HUBS in .env)
#   2. uncomment the aws.region_c provider below
#   3. uncomment the region C blocks in main.tf
#
# See "Adding a third region" in README.md, and read the note there about
# Transit Gateway peering not being transitive before you do it.

provider "aws" {
  alias  = "region_a"
  region = var.hubs["a"].aws_region

  default_tags {
    tags = local.mandatory_tags
  }
}

provider "aws" {
  alias  = "region_b"
  region = var.hubs["b"].aws_region

  default_tags {
    tags = local.mandatory_tags
  }
}

# provider "aws" {
#   alias  = "region_c"
#   region = var.hubs["c"].aws_region
#
#   default_tags {
#     tags = local.mandatory_tags
#   }
# }

# ── Application accounts (spokes) ──────────────────────────────────────────────
#
# Same region as hub A, different AWS account, reached by assuming a role there.
# The assume_role block is dynamic so that these providers collapse to plain
# hub-account providers when `spokes` is empty - the spoke modules are then
# count = 0 and nothing uses them.

provider "aws" {
  alias  = "spoke_1"
  region = var.hubs["a"].aws_region

  dynamic "assume_role" {
    for_each = contains(keys(var.spokes), "1") ? [var.spokes["1"]] : []
    content {
      role_arn     = assume_role.value.role_arn
      session_name = "${var.name_prefix}-terraform"
    }
  }

  default_tags {
    tags = local.mandatory_tags
  }
}

provider "aws" {
  alias  = "spoke_2"
  region = var.hubs["a"].aws_region

  dynamic "assume_role" {
    for_each = contains(keys(var.spokes), "2") ? [var.spokes["2"]] : []
    content {
      role_arn     = assume_role.value.role_arn
      session_name = "${var.name_prefix}-terraform"
    }
  }

  default_tags {
    tags = local.mandatory_tags
  }
}
