# Nothing here is sensitive. This configuration never handles an Atlas
# connection string, an Atlas API key or a database credential, so there is
# nothing of that kind to mark sensitive or to accidentally print.

output "regions" {
  description = "AWS region behind each region key in this lab."
  value       = { for key in local.hub_keys : key => var.hubs[key].aws_region }
}

output "transit_gateways" {
  description = "Transit Gateway and route table IDs per region key."
  value = {
    a = {
      transit_gateway_id = module.tgw_a.transit_gateway_id
      route_table_id     = module.tgw_a.transit_gateway_route_table_id
      amazon_side_asn    = module.tgw_a.amazon_side_asn
    }
    b = {
      transit_gateway_id = module.tgw_b.transit_gateway_id
      route_table_id     = module.tgw_b.transit_gateway_route_table_id
      amazon_side_asn    = module.tgw_b.amazon_side_asn
    }
  }
}

output "transit_gateway_peering_attachment_id" {
  description = "ID of the direct inter-region Transit Gateway peering attachment between region A and region B."
  value       = aws_ec2_transit_gateway_peering_attachment.a_to_b.id
}

output "hub_vpcs" {
  description = "Hub VPC facts per region key."
  value = {
    a = {
      vpc_id             = module.hub_a.vpc_id
      vpc_cidr_block     = module.hub_a.vpc_cidr_block
      availability_zones = module.hub_a.availability_zones
      subnet_ids         = module.hub_a.subnet_ids
      security_group_id  = module.hub_a.security_group_id
    }
    b = {
      vpc_id             = module.hub_b.vpc_id
      vpc_cidr_block     = module.hub_b.vpc_cidr_block
      availability_zones = module.hub_b.availability_zones
      subnet_ids         = module.hub_b.subnet_ids
      security_group_id  = module.hub_b.security_group_id
    }
  }
}

output "atlas_interface_endpoints" {
  description = <<-EOT
    Interface VPC endpoint IDs per region key and label. These are the IDs you
    paste back into the Atlas private endpoint for the matching project and
    region so Atlas can finish wiring its side of the PrivateLink connection.
  EOT
  value = {
    a = module.hub_a.endpoint_ids
    b = module.hub_b.endpoint_ids
  }
}

output "atlas_interface_endpoint_dns_names" {
  description = "DNS names AWS generated for each interface endpoint. The Atlas private-endpoint-aware hostnames resolve to these; private DNS is deliberately left disabled on the endpoints so Atlas stays the authority."
  value = {
    a = module.hub_a.endpoint_dns_names
    b = module.hub_b.endpoint_dns_names
  }
}

output "client_vpc" {
  description = "Client VPC facts."
  value = {
    region_key     = var.client.region_key
    aws_region     = var.hubs[var.client.region_key].aws_region
    vpc_id         = module.client.vpc_id
    vpc_cidr_block = module.client.vpc_cidr_block
    subnet_ids     = module.client.subnet_ids
  }
}

output "internet_egress" {
  description = <<-EOT
    State of the optional NAT egress path, which exists only so the test VM can
    install mongosh. The VM has no public IP either way, and the MongoDB port
    range is only ever allowed towards the hub VPC CIDRs, so Atlas stays
    reachable over PrivateLink only. Set CLIENT_INTERNET_EGRESS=false and
    re-run ./deploy.sh to remove the NAT gateway once mongosh is installed.
  EOT
  value = {
    enabled               = module.client.internet_egress_enabled
    nat_gateway_public_ip = module.client.nat_gateway_public_ip
  }
}

output "test_instance_id" {
  description = "Instance ID of the test VM. It has no public IP and no SSH; reach it with Session Manager."
  value       = module.client.instance_id
}

output "start_session_command" {
  description = "Command that opens a Session Manager shell on the test VM."
  value       = "aws ssm start-session --region ${var.hubs[var.client.region_key].aws_region} --target ${module.client.instance_id}"
}

output "connectivity_test_command" {
  description = "One-shot reachability test across both regions, run through Session Manager without opening an interactive shell."
  value       = "aws ssm start-session --region ${var.hubs[var.client.region_key].aws_region} --target ${module.client.instance_id} --document-name AWS-StartInteractiveCommand --parameters command='sudo atlas-plink-test'"
}

output "query_test_command" {
  description = "Per-region query test: an explicit read from the secondary in the primary's region and from a secondary in the other region. Interactive - it prompts for the connection string and password, which are never stored."
  value       = "aws ssm start-session --region ${var.hubs[var.client.region_key].aws_region} --target ${module.client.instance_id} --document-name AWS-StartInteractiveCommand --parameters command='atlas-plink-query'"
}

output "spokes" {
  description = "Application accounts consuming the hub's interface endpoints. They own no endpoint and are registered with Atlas nowhere - that is the consolidation."
  value = merge(
    contains(keys(var.spokes), "1") ? {
      "1" = {
        account_id            = var.spokes["1"].account_id
        vpc_id                = module.spoke_1[0].vpc_id
        vpc_cidr_block        = module.spoke_1[0].vpc_cidr_block
        instance_id           = module.spoke_1[0].instance_id
        start_session_command = "aws ssm start-session --region ${var.hubs["a"].aws_region} --target ${module.spoke_1[0].instance_id}  # requires credentials for account ${var.spokes["1"].account_id}"
      }
    } : {},
    contains(keys(var.spokes), "2") ? {
      "2" = {
        account_id            = var.spokes["2"].account_id
        vpc_id                = module.spoke_2[0].vpc_id
        vpc_cidr_block        = module.spoke_2[0].vpc_cidr_block
        instance_id           = module.spoke_2[0].instance_id
        start_session_command = "aws ssm start-session --region ${var.hubs["a"].aws_region} --target ${module.spoke_2[0].instance_id}  # requires credentials for account ${var.spokes["2"].account_id}"
      }
    } : {},
  )
}

output "privatelink_footprint" {
  description = "The headline number: interface endpoints and ENIs serving the whole estate, against the number of consuming accounts and VPCs."
  value = {
    atlas_endpoint_services   = length(local.hub_keys)
    interface_endpoints       = sum([for key in local.hub_keys : length(var.hubs[key].atlas_endpoint_services)])
    endpoint_enis             = sum([for key in local.hub_keys : length(var.hubs[key].atlas_endpoint_services) * length(var.hubs[key].subnet_cidrs)])
    consuming_aws_accounts    = 1 + length(var.spokes)
    consuming_vpcs            = 1 + length(var.spokes)
    clusters_served           = "every cluster in the Atlas project, in these regions"
    endpoints_per_new_account = 0
  }
}
