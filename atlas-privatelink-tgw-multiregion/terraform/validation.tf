# Cross-variable validation.
#
# A `validation` block can only look at the variable it belongs to, so the rules
# that span variables live here as preconditions on a null resource. They are
# evaluated during `terraform plan`, before any AWS API call, and they fail the
# run rather than warn.

resource "terraform_data" "preflight" {
  input = {
    vpcs    = local.vpc_cidrs
    subnets = { for label, set in local.subnet_sets : label => set.subnets }
  }

  lifecycle {
    precondition {
      condition     = contains(keys(var.hubs), var.client.region_key)
      error_message = "client.region_key (\"${var.client.region_key}\") must name one of the hubs: ${join(", ", local.hub_keys)}. The client VPC attaches to that region's Transit Gateway."
    }

    precondition {
      condition     = !var.client.internet_egress_enabled || var.client.nat_subnet_cidr != ""
      error_message = "client.nat_subnet_cidr must be set when client.internet_egress_enabled is true. The NAT gateway needs a subnet with a route to an internet gateway, and it must not be one of the private subnets the test VM sits in. A /28 is plenty."
    }

    precondition {
      condition     = length(local.badly_sized_vpc_cidrs) == 0
      error_message = "Invalid VPC CIDR size:\n  ${join("\n  ", local.badly_sized_vpc_cidrs)}"
    }

    precondition {
      condition     = length(local.overlapping_vpc_cidrs) == 0
      error_message = "VPC CIDRs overlap. Transit Gateway routing needs unique, non-overlapping prefixes:\n  ${join("\n  ", local.overlapping_vpc_cidrs)}"
    }

    precondition {
      condition     = length(local.subnets_outside_their_vpc) == 0
      error_message = "Subnet CIDRs must sit inside their own VPC CIDR:\n  ${join("\n  ", local.subnets_outside_their_vpc)}"
    }

    precondition {
      condition     = length(local.overlapping_subnets) == 0
      error_message = "Subnet CIDRs overlap inside a VPC:\n  ${join("\n  ", local.overlapping_subnets)}"
    }

    precondition {
      condition     = var.allow_single_az_endpoints || length(local.single_az_hubs) == 0
      error_message = <<-EOT
        Each hub should place interface endpoint ENIs in at least two Availability Zones:
          ${join("\n  ", local.single_az_hubs)}
        An interface endpoint bills per ENI per hour, so a second AZ roughly doubles the
        endpoint's hourly cost - but a single-AZ endpoint makes that AZ a single point of
        failure for the whole region's Atlas path. If the region or the Atlas endpoint
        service genuinely offers only one AZ, set allow_single_az_endpoints = true
        (ALLOW_SINGLE_AZ_ENDPOINTS=true in .env) to accept that trade-off deliberately.
      EOT
    }
  }
}
