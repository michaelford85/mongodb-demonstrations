# Hub VPC: the attachment point between AWS networking and the Atlas
# PrivateLink endpoint service in this region.
#
# Atlas is NOT a VPC peer and NOT a Transit Gateway attachment. The interface
# endpoints below are the only thing that touches Atlas; everything else in the
# lab exists to deliver packets to these ENIs.
#
# There is no internet gateway, no NAT gateway and no public subnet here.

data "aws_availability_zones" "available" {
  state = "available"

  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  subnets = {
    for idx, cidr in var.subnet_cidrs :
    format("%02d", idx) => {
      cidr_block        = cidr
      availability_zone = length(var.availability_zones) > 0 ? var.availability_zones[idx] : data.aws_availability_zones.available.names[idx]
    }
  }
}

resource "aws_vpc" "this" {
  cidr_block = var.vpc_cidr_block

  # The endpoint's DNS names, and the Atlas private-endpoint-aware hostnames
  # that CNAME to them, are resolved by the VPC resolver. Both must stay on.
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.name_prefix}-hub-vpc-${var.region_key}"
    Role = "atlas-privatelink-hub"
  }

  # Protected by default; ./teardown.sh lifts this deliberately.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_subnet" "endpoints" {
  for_each = local.subnets

  vpc_id            = aws_vpc.this.id
  cidr_block        = each.value.cidr_block
  availability_zone = each.value.availability_zone

  # No public addressing anywhere in this lab.
  map_public_ip_on_launch = false

  tags = {
    Name = "${var.name_prefix}-hub-subnet-${var.region_key}-${each.value.availability_zone}"
  }
}

resource "aws_route_table" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-hub-rt-${var.region_key}"
  }
}

resource "aws_route_table_association" "endpoints" {
  for_each = aws_subnet.endpoints

  subnet_id      = each.value.id
  route_table_id = aws_route_table.this.id
}

# Return path for traffic that arrived from the client VPC. Only the explicit
# client prefixes are routed at the Transit Gateway - never 0.0.0.0/0.
resource "aws_route" "to_client" {
  for_each = toset(var.client_cidr_blocks)

  route_table_id         = aws_route_table.this.id
  destination_cidr_block = each.value
  transit_gateway_id     = var.transit_gateway_id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment.this]
}

# ── Endpoint security group ────────────────────────────────────────────────────
# Atlas publishes one TCP port per node on a private endpoint, starting at 1024,
# so the whole ephemeral range has to be open from the client side.
#
# Security group references cannot cross regions, so the cross-region path is
# authorised by the client VPC's CIDR. Keep those CIDRs tight - this is the only
# thing standing between the client prefix and the Atlas endpoint.
resource "aws_security_group" "endpoints" {
  name        = "${var.name_prefix}-hub-ep-sg-${var.region_key}"
  description = "Atlas interface endpoint ENIs in hub ${var.region_key}"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-hub-ep-sg-${var.region_key}"
  }
}

resource "aws_vpc_security_group_ingress_rule" "mongodb_from_client" {
  for_each = toset(var.client_cidr_blocks)

  security_group_id = aws_security_group.endpoints.id
  description       = "MongoDB over AWS PrivateLink from client CIDR ${each.value}"
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 1024
  to_port           = 65535
}

# No egress rules: endpoint ENIs only answer connections, and security groups
# are stateful, so replies leave without an egress allowance.

# ── Interface endpoints to the existing Atlas endpoint services ────────────────
resource "aws_vpc_endpoint" "atlas" {
  for_each = var.atlas_endpoint_services

  vpc_id            = aws_vpc.this.id
  service_name      = each.value
  vpc_endpoint_type = "Interface"
  subnet_ids        = [for subnet in aws_subnet.endpoints : subnet.id]

  security_group_ids = [aws_security_group.endpoints.id]

  # Must stay false. Atlas owns the private-endpoint-aware hostnames: the SRV
  # record and the per-node CNAMEs in mongodb.net point at this endpoint's
  # generated DNS names. Enabling private DNS here would hijack that resolution
  # and break the mapping between Atlas nodes and endpoint ports.
  private_dns_enabled = false

  tags = {
    Name          = "${var.name_prefix}-atlas-ep-${var.region_key}-${each.key}"
    AtlasEndpoint = each.key
  }

  # Protected by default; ./teardown.sh lifts this deliberately. Deleting an
  # interface endpoint also invalidates the Atlas-side private endpoint that
  # references it.
  lifecycle {
    prevent_destroy = true
  }
}

# ── Transit Gateway attachment ─────────────────────────────────────────────────
# Association and propagation are declared in the root module against the lab's
# explicit TGW route table, so they are switched off here.
resource "aws_ec2_transit_gateway_vpc_attachment" "this" {
  transit_gateway_id = var.transit_gateway_id
  vpc_id             = aws_vpc.this.id
  subnet_ids         = [for subnet in aws_subnet.endpoints : subnet.id]

  dns_support                                     = "enable"
  ipv6_support                                    = "disable"
  appliance_mode_support                          = "disable"
  transit_gateway_default_route_table_association = false
  transit_gateway_default_route_table_propagation = false

  tags = {
    Name = "${var.name_prefix}-hub-attach-${var.region_key}"
  }
}
