# atlas-privatelink-tgw-multiregion
#
# Proves that a workload VM in AWS region A can reach the region-A *and* the
# region-B members of an existing multi-region Atlas replica set without any
# public Atlas connectivity.
#
# What this configuration does NOT do: it does not create, modify or read the
# Atlas cluster, the Atlas project, or the Atlas private endpoint services. They
# already exist. No Atlas provider is configured and no Atlas API credentials
# are accepted, so nothing Atlas-side can leak into this state file.
#
# Atlas is not a Transit Gateway attachment and not a VPC peer. The hub VPC's
# interface endpoint is the attachment point to the Atlas PrivateLink endpoint
# service, and that is the only boundary crossing in the design.

# ── Region A: Transit Gateway ──────────────────────────────────────────────────

module "tgw_a" {
  source = "./modules/transit-gateway"

  providers = {
    aws = aws.region_a
  }

  name_prefix     = var.name_prefix
  region_key      = "a"
  amazon_side_asn = local.hub_asns["a"]

  depends_on = [terraform_data.preflight]
}

# ── Region B: Transit Gateway ──────────────────────────────────────────────────

module "tgw_b" {
  source = "./modules/transit-gateway"

  providers = {
    aws = aws.region_b
  }

  name_prefix     = var.name_prefix
  region_key      = "b"
  amazon_side_asn = local.hub_asns["b"]

  depends_on = [terraform_data.preflight]
}

# ── Region A: hub VPC with the Atlas interface endpoint(s) ─────────────────────

module "hub_a" {
  source = "./modules/hub-vpc"

  providers = {
    aws = aws.region_a
  }

  name_prefix             = var.name_prefix
  region_key              = "a"
  vpc_cidr_block          = var.hubs["a"].vpc_cidr_block
  subnet_cidrs            = var.hubs["a"].subnet_cidrs
  availability_zones      = var.hubs["a"].availability_zones
  atlas_endpoint_services = var.hubs["a"].atlas_endpoint_services
  client_cidr_blocks      = local.client_cidr_blocks
  transit_gateway_id      = module.tgw_a.transit_gateway_id
}

# ── Region B: hub VPC with the Atlas interface endpoint(s) ─────────────────────

module "hub_b" {
  source = "./modules/hub-vpc"

  providers = {
    aws = aws.region_b
  }

  name_prefix             = var.name_prefix
  region_key              = "b"
  vpc_cidr_block          = var.hubs["b"].vpc_cidr_block
  subnet_cidrs            = var.hubs["b"].subnet_cidrs
  availability_zones      = var.hubs["b"].availability_zones
  atlas_endpoint_services = var.hubs["b"].atlas_endpoint_services
  client_cidr_blocks      = local.client_cidr_blocks
  transit_gateway_id      = module.tgw_b.transit_gateway_id
}

# ── Region A: client VPC and the test VM ───────────────────────────────────────

module "client" {
  source = "./modules/client-vpc"

  providers = {
    aws = aws.region_a
  }

  name_prefix             = var.name_prefix
  region_key              = var.client.region_key
  vpc_cidr_block          = var.client.vpc_cidr_block
  subnet_cidrs            = var.client.subnet_cidrs
  availability_zones      = var.client.availability_zones
  instance_type           = var.client.instance_type
  internet_egress_enabled = var.client.internet_egress_enabled
  nat_subnet_cidr         = var.client.nat_subnet_cidr
  transit_gateway_id      = module.tgw_a.transit_gateway_id
  hub_cidr_blocks         = local.hub_cidr_blocks
  test_ports              = var.test_ports
  test_port_scan_range    = var.test_port_scan_range
  mongosh_s3_uri          = var.mongosh_s3_uri
  endpoint_targets        = local.endpoint_targets
}

# ── Transit Gateway route tables: associations and propagations ────────────────
#
# Default association and propagation are disabled on both gateways, so every
# line below is a deliberate statement about what may route where.

# Region A: the client VPC and the local hub VPC.
resource "aws_ec2_transit_gateway_route_table_association" "client_a" {
  provider = aws.region_a

  transit_gateway_attachment_id  = module.client.transit_gateway_attachment_id
  transit_gateway_route_table_id = module.tgw_a.transit_gateway_route_table_id
}

resource "aws_ec2_transit_gateway_route_table_propagation" "client_a" {
  provider = aws.region_a

  transit_gateway_attachment_id  = module.client.transit_gateway_attachment_id
  transit_gateway_route_table_id = module.tgw_a.transit_gateway_route_table_id
}

resource "aws_ec2_transit_gateway_route_table_association" "hub_a" {
  provider = aws.region_a

  transit_gateway_attachment_id  = module.hub_a.transit_gateway_attachment_id
  transit_gateway_route_table_id = module.tgw_a.transit_gateway_route_table_id
}

resource "aws_ec2_transit_gateway_route_table_propagation" "hub_a" {
  provider = aws.region_a

  transit_gateway_attachment_id  = module.hub_a.transit_gateway_attachment_id
  transit_gateway_route_table_id = module.tgw_a.transit_gateway_route_table_id
}

# Region B: the hub VPC only. There is no workload in region B.
resource "aws_ec2_transit_gateway_route_table_association" "hub_b" {
  provider = aws.region_b

  transit_gateway_attachment_id  = module.hub_b.transit_gateway_attachment_id
  transit_gateway_route_table_id = module.tgw_b.transit_gateway_route_table_id
}

resource "aws_ec2_transit_gateway_route_table_propagation" "hub_b" {
  provider = aws.region_b

  transit_gateway_attachment_id  = module.hub_b.transit_gateway_attachment_id
  transit_gateway_route_table_id = module.tgw_b.transit_gateway_route_table_id
}

# ── Inter-region Transit Gateway peering ───────────────────────────────────────
#
# Transit Gateway peering is NOT transitive: a packet that arrives on a peering
# attachment is never forwarded out of another peering attachment. With two
# regions that is invisible. With three it matters - see "Adding a third region"
# in README.md, which requires a full mesh rather than A -> B -> C.
#
# Peering attachments also do not participate in route propagation, so the
# routes that use them are static by necessity as well as by choice.

resource "aws_ec2_transit_gateway_peering_attachment" "a_to_b" {
  provider = aws.region_a

  transit_gateway_id      = module.tgw_a.transit_gateway_id
  peer_transit_gateway_id = module.tgw_b.transit_gateway_id
  peer_region             = var.hubs["b"].aws_region

  tags = {
    Name = "${var.name_prefix}-tgw-peer-a-b"
    Side = "requester"
  }

  # Protected by default; ./teardown.sh lifts this deliberately.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_ec2_transit_gateway_peering_attachment_accepter" "b_from_a" {
  provider = aws.region_b

  transit_gateway_attachment_id = aws_ec2_transit_gateway_peering_attachment.a_to_b.id

  tags = {
    Name = "${var.name_prefix}-tgw-peer-a-b"
    Side = "accepter"
  }

  # Protected by default; ./teardown.sh lifts this deliberately.
  lifecycle {
    prevent_destroy = true
  }
}

# The peering attachment has to be associated with a route table on each side,
# otherwise arriving packets have no route table to be looked up in.
resource "aws_ec2_transit_gateway_route_table_association" "peering_a" {
  provider = aws.region_a

  transit_gateway_attachment_id  = aws_ec2_transit_gateway_peering_attachment.a_to_b.id
  transit_gateway_route_table_id = module.tgw_a.transit_gateway_route_table_id

  depends_on = [aws_ec2_transit_gateway_peering_attachment_accepter.b_from_a]
}

resource "aws_ec2_transit_gateway_route_table_association" "peering_b" {
  provider = aws.region_b

  transit_gateway_attachment_id  = aws_ec2_transit_gateway_peering_attachment_accepter.b_from_a.id
  transit_gateway_route_table_id = module.tgw_b.transit_gateway_route_table_id
}

# ── Explicit cross-region routes, both directions ──────────────────────────────

# A -> B: reach every remote hub prefix over the peering attachment.
resource "aws_ec2_transit_gateway_route" "a_to_remote_hubs" {
  provider = aws.region_a

  for_each = toset(local.remote_hub_cidrs_from_client_region)

  transit_gateway_route_table_id = module.tgw_a.transit_gateway_route_table_id
  destination_cidr_block         = each.value
  transit_gateway_attachment_id  = aws_ec2_transit_gateway_peering_attachment.a_to_b.id

  depends_on = [aws_ec2_transit_gateway_route_table_association.peering_a]
}

# B -> A: return path for every consuming prefix - the hub account's client VPC
# and each application account's spoke VPC. Without these the outbound half
# works and the replies are silently dropped at the region B gateway. Every new
# application account adds one route here; that is the only region-B change
# onboarding requires.
resource "aws_ec2_transit_gateway_route" "b_to_client" {
  provider = aws.region_b

  for_each = toset(local.client_cidr_blocks)

  transit_gateway_route_table_id = module.tgw_b.transit_gateway_route_table_id
  destination_cidr_block         = each.value
  transit_gateway_attachment_id  = aws_ec2_transit_gateway_peering_attachment_accepter.b_from_a.id

  depends_on = [aws_ec2_transit_gateway_route_table_association.peering_b]
}

# ── Application accounts (spokes) ──────────────────────────────────────────────
#
# THE POINT OF THIS SECTION: these accounts consume the SAME two interface
# endpoints created above. They create no endpoint of their own and register
# nothing with Atlas, so the number of PrivateLink endpoints stays at two
# however many application accounts are onboarded.
#
# What makes that possible is that private DNS is disabled on the Atlas
# endpoints. Atlas keeps ownership of the hostnames, and the records it
# publishes in mongodb.net are public DNS entries pointing at the endpoints'
# private addresses - so any VPC in any account resolves them correctly with no
# Route 53 private hosted zone, no zone sharing and no resolver rules.
#
# (The SSM endpoints inside each spoke VPC are the counter-example: they use
# private DNS, so they cannot be shared the same way and each spoke builds its
# own.)

# Share the region-A Transit Gateway with the application accounts. Accounts in
# the same AWS Organization accept automatically once the management account has
# run: aws ram enable-sharing-with-aws-organization
resource "aws_ram_resource_share" "tgw_a" {
  count    = length(var.spokes) > 0 ? 1 : 0
  provider = aws.region_a

  name                      = "${var.name_prefix}-tgw-a"
  allow_external_principals = var.ram_allow_external_principals

  tags = {
    Name = "${var.name_prefix}-tgw-a"
  }
}

resource "aws_ram_resource_association" "tgw_a" {
  count    = length(var.spokes) > 0 ? 1 : 0
  provider = aws.region_a

  resource_arn       = module.tgw_a.transit_gateway_arn
  resource_share_arn = aws_ram_resource_share.tgw_a[0].arn
}

resource "aws_ram_principal_association" "spokes" {
  for_each = var.spokes
  provider = aws.region_a

  principal          = each.value.account_id
  resource_share_arn = aws_ram_resource_share.tgw_a[0].arn
}

# ── Spoke 1 ────────────────────────────────────────────────────────────────────

module "spoke_1" {
  count  = contains(keys(var.spokes), "1") ? 1 : 0
  source = "./modules/client-vpc"

  providers = {
    aws = aws.spoke_1
  }

  name_prefix             = var.name_prefix
  name_suffix             = "spoke-1"
  region_key              = "a"
  vpc_cidr_block          = var.spokes["1"].vpc_cidr_block
  subnet_cidrs            = var.spokes["1"].subnet_cidrs
  availability_zones      = var.spokes["1"].availability_zones
  instance_type           = var.spokes["1"].instance_type
  internet_egress_enabled = var.spokes["1"].internet_egress_enabled
  nat_subnet_cidr         = var.spokes["1"].nat_subnet_cidr
  transit_gateway_id      = module.tgw_a.transit_gateway_id
  tgw_cross_account       = true
  hub_cidr_blocks         = local.hub_cidr_blocks
  test_ports              = var.test_ports
  test_port_scan_range    = var.test_port_scan_range
  mongosh_s3_uri          = var.mongosh_s3_uri
  endpoint_targets        = local.endpoint_targets

  depends_on = [aws_ram_principal_association.spokes]
}

# Cross-account attachments are not auto-accepted: auto_accept_shared_attachments
# stays disabled on the gateway, so the hub account accepts each one explicitly
# and decides, here, what it may route to.
resource "aws_ec2_transit_gateway_vpc_attachment_accepter" "spoke_1" {
  count    = contains(keys(var.spokes), "1") ? 1 : 0
  provider = aws.region_a

  transit_gateway_attachment_id                   = module.spoke_1[0].transit_gateway_attachment_id
  transit_gateway_default_route_table_association = false
  transit_gateway_default_route_table_propagation = false

  tags = {
    Name = "${var.name_prefix}-spoke-1-attach-a"
  }
}

resource "aws_ec2_transit_gateway_route_table_association" "spoke_1" {
  count    = contains(keys(var.spokes), "1") ? 1 : 0
  provider = aws.region_a

  transit_gateway_attachment_id  = aws_ec2_transit_gateway_vpc_attachment_accepter.spoke_1[0].id
  transit_gateway_route_table_id = module.tgw_a.transit_gateway_route_table_id
}

resource "aws_ec2_transit_gateway_route_table_propagation" "spoke_1" {
  count    = contains(keys(var.spokes), "1") ? 1 : 0
  provider = aws.region_a

  transit_gateway_attachment_id  = aws_ec2_transit_gateway_vpc_attachment_accepter.spoke_1[0].id
  transit_gateway_route_table_id = module.tgw_a.transit_gateway_route_table_id
}

# ── Spoke 2 ────────────────────────────────────────────────────────────────────

module "spoke_2" {
  count  = contains(keys(var.spokes), "2") ? 1 : 0
  source = "./modules/client-vpc"

  providers = {
    aws = aws.spoke_2
  }

  name_prefix             = var.name_prefix
  name_suffix             = "spoke-2"
  region_key              = "a"
  vpc_cidr_block          = var.spokes["2"].vpc_cidr_block
  subnet_cidrs            = var.spokes["2"].subnet_cidrs
  availability_zones      = var.spokes["2"].availability_zones
  instance_type           = var.spokes["2"].instance_type
  internet_egress_enabled = var.spokes["2"].internet_egress_enabled
  nat_subnet_cidr         = var.spokes["2"].nat_subnet_cidr
  transit_gateway_id      = module.tgw_a.transit_gateway_id
  tgw_cross_account       = true
  hub_cidr_blocks         = local.hub_cidr_blocks
  test_ports              = var.test_ports
  test_port_scan_range    = var.test_port_scan_range
  mongosh_s3_uri          = var.mongosh_s3_uri
  endpoint_targets        = local.endpoint_targets

  depends_on = [aws_ram_principal_association.spokes]
}

resource "aws_ec2_transit_gateway_vpc_attachment_accepter" "spoke_2" {
  count    = contains(keys(var.spokes), "2") ? 1 : 0
  provider = aws.region_a

  transit_gateway_attachment_id                   = module.spoke_2[0].transit_gateway_attachment_id
  transit_gateway_default_route_table_association = false
  transit_gateway_default_route_table_propagation = false

  tags = {
    Name = "${var.name_prefix}-spoke-2-attach-a"
  }
}

resource "aws_ec2_transit_gateway_route_table_association" "spoke_2" {
  count    = contains(keys(var.spokes), "2") ? 1 : 0
  provider = aws.region_a

  transit_gateway_attachment_id  = aws_ec2_transit_gateway_vpc_attachment_accepter.spoke_2[0].id
  transit_gateway_route_table_id = module.tgw_a.transit_gateway_route_table_id
}

resource "aws_ec2_transit_gateway_route_table_propagation" "spoke_2" {
  count    = contains(keys(var.spokes), "2") ? 1 : 0
  provider = aws.region_a

  transit_gateway_attachment_id  = aws_ec2_transit_gateway_vpc_attachment_accepter.spoke_2[0].id
  transit_gateway_route_table_id = module.tgw_a.transit_gateway_route_table_id
}

# ── Adding a third region ──────────────────────────────────────────────────────
#
# Uncomment aws.region_c in providers.tf, add a "c" entry to HUBS, then the
# blocks below. Note the peering: C peers directly with A *and* with B. Do not
# expect traffic to reach C by transiting B.
#
# module "tgw_c" {
#   source          = "./modules/transit-gateway"
#   providers       = { aws = aws.region_c }
#   name_prefix     = var.name_prefix
#   region_key      = "c"
#   amazon_side_asn = local.hub_asns["c"]
#   depends_on      = [terraform_data.preflight]
# }
#
# module "hub_c" {
#   source                  = "./modules/hub-vpc"
#   providers               = { aws = aws.region_c }
#   name_prefix             = var.name_prefix
#   region_key              = "c"
#   vpc_cidr_block          = var.hubs["c"].vpc_cidr_block
#   subnet_cidrs            = var.hubs["c"].subnet_cidrs
#   availability_zones      = var.hubs["c"].availability_zones
#   atlas_endpoint_services = var.hubs["c"].atlas_endpoint_services
#   client_cidr_blocks      = local.client_cidr_blocks
#   transit_gateway_id      = module.tgw_c.transit_gateway_id
# }
#
# ...plus the route table association/propagation pair for hub_c, an
# a_to_c peering attachment and accepter, a b_to_c peering attachment and
# accepter if regions B and C ever need to talk, and the matching static
# routes in both directions for each peering.
