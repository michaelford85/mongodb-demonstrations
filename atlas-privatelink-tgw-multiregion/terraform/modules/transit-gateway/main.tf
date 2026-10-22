# One Transit Gateway per lab region, with an explicit route table.
#
# Default association and propagation are switched off so that nothing lands in
# a route table by accident: every association, every propagation and every
# static route is declared in the root module and visible in the plan.

resource "aws_ec2_transit_gateway" "this" {
  description                     = "${var.name_prefix} region ${var.region_key} - Atlas PrivateLink hub transit"
  amazon_side_asn                 = var.amazon_side_asn
  default_route_table_association = "disable"
  default_route_table_propagation = "disable"
  auto_accept_shared_attachments  = "disable"
  dns_support                     = "enable"
  vpn_ecmp_support                = "disable"

  tags = {
    Name = "${var.name_prefix}-tgw-${var.region_key}"
  }

  # Protected by default. ./teardown.sh writes a *_override.tf file that flips
  # this to false for a deliberate teardown - see README.md, "Cleanup".
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_ec2_transit_gateway_route_table" "this" {
  transit_gateway_id = aws_ec2_transit_gateway.this.id

  tags = {
    Name = "${var.name_prefix}-tgw-rt-${var.region_key}"
  }
}
