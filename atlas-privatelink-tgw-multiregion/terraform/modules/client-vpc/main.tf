# Client VPC: the workload side of the lab.
#
# The test VM has no public IP, no key pair and no inbound rule of any kind.
# Operator access is SSM Session Manager.
#
# Optional NAT egress (internet_egress_enabled, on by default) exists for one
# reason: installing mongosh from repo.mongodb.org. It does NOT weaken the
# PrivateLink claim, because the VM's security group only ever allows the
# MongoDB port range towards the hub VPC CIDRs. Ports 80 and 443 are the only
# thing allowed out to the internet, and Atlas does not serve the wire protocol
# on either. See the "Proving the path is private" section of the README, and
# set CLIENT_INTERNET_EGRESS=false once mongosh is installed to delete the NAT
# gateway and the default route entirely.

data "aws_region" "current" {}

data "aws_availability_zones" "available" {
  state = "available"

  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

locals {
  suffix = var.name_suffix != "" ? "-${var.name_suffix}" : ""

  subnets = {
    for idx, cidr in var.subnet_cidrs :
    format("%02d", idx) => {
      cidr_block        = cidr
      availability_zone = length(var.availability_zones) > 0 ? var.availability_zones[idx] : data.aws_availability_zones.available.names[idx]
    }
  }

  first_subnet_key = format("%02d", 0)

  # Interface endpoints that keep the VM reachable and patchable without any
  # route to the internet. private_dns_enabled is true here on purpose: these
  # are AWS service endpoints, not the Atlas endpoints.
  ssm_services = toset(["ssm", "ssmmessages", "ec2messages"])

  # EC2 caps user data at 16 KB. The bootstrap carries four scripts and the
  # per-region query test, which is comfortably over that raw, so it is gzipped
  # and base64-encoded: cloud-init detects the gzip magic bytes and unpacks it
  # before running anything. aws_instance.test asserts the encoded size below.
  # Atlas port blocks are project-specific, so the heuristic scan covers a
  # range; `atlas-plink-test --srv` bypasses guessing entirely.
  probe_ports = distinct(concat(
    range(var.test_port_scan_range.start, var.test_port_scan_range.end + 1),
    var.test_ports,
  ))

  user_data_raw = templatefile("${path.module}/templates/user_data.sh.tftpl", {
    endpoint_targets = var.endpoint_targets
    test_ports       = local.probe_ports
    mongosh_s3_uri   = var.mongosh_s3_uri
    region_query_js  = file("${path.module}/files/region-query-test.js")
  })

  user_data_encoded   = base64gzip(local.user_data_raw)
  user_data_max_bytes = 16384

  mongosh_enabled = var.mongosh_s3_uri != ""
  mongosh_path    = local.mongosh_enabled ? replace(var.mongosh_s3_uri, "s3://", "") : ""
  mongosh_bucket  = local.mongosh_enabled ? split("/", local.mongosh_path)[0] : ""
  mongosh_key     = local.mongosh_enabled ? join("/", slice(split("/", local.mongosh_path), 1, length(split("/", local.mongosh_path)))) : ""
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr_block
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.name_prefix}${local.suffix}-client-vpc-${var.region_key}"
    Role = "atlas-privatelink-client"
  }

  # Protected by default; ./teardown.sh lifts this deliberately.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_subnet" "private" {
  for_each = local.subnets

  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value.cidr_block
  availability_zone       = each.value.availability_zone
  map_public_ip_on_launch = false

  tags = {
    Name = "${var.name_prefix}${local.suffix}-client-subnet-${var.region_key}-${each.value.availability_zone}"
  }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}${local.suffix}-client-rt-${var.region_key}"
  }
}

resource "aws_route_table_association" "private" {
  for_each = aws_subnet.private

  subnet_id      = each.value.id
  route_table_id = aws_route_table.private.id
}

# One explicit route per hub prefix - local and remote. A 0.0.0.0/0 route to the
# Transit Gateway would be shorter and would also blackhole every other
# destination in a VPC that has no other egress, so it is not used.
resource "aws_route" "to_hubs" {
  for_each = toset(var.hub_cidr_blocks)

  route_table_id         = aws_route_table.private.id
  destination_cidr_block = each.value
  transit_gateway_id     = var.transit_gateway_id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment.this]
}

# ── Optional NAT egress, for package installation only ─────────────────────────
#
# The only public IP in this lab is the NAT gateway's elastic IP. It carries
# outbound traffic only; nothing in this VPC is reachable from the internet.

resource "aws_internet_gateway" "this" {
  count = var.internet_egress_enabled ? 1 : 0

  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}${local.suffix}-client-igw-${var.region_key}"
  }
}

resource "aws_subnet" "nat" {
  count = var.internet_egress_enabled ? 1 : 0

  vpc_id            = aws_vpc.this.id
  cidr_block        = var.nat_subnet_cidr
  availability_zone = local.subnets[local.first_subnet_key].availability_zone

  # Even here: no automatic public addressing. The NAT gateway gets an explicit
  # elastic IP; nothing else is ever launched in this subnet.
  map_public_ip_on_launch = false

  tags = {
    Name = "${var.name_prefix}${local.suffix}-client-nat-subnet-${var.region_key}"
    Role = "nat-egress-only"
  }
}

resource "aws_route_table" "nat" {
  count = var.internet_egress_enabled ? 1 : 0

  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}${local.suffix}-client-nat-rt-${var.region_key}"
  }
}

resource "aws_route" "nat_default" {
  count = var.internet_egress_enabled ? 1 : 0

  route_table_id         = aws_route_table.nat[0].id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this[0].id
}

resource "aws_route_table_association" "nat" {
  count = var.internet_egress_enabled ? 1 : 0

  subnet_id      = aws_subnet.nat[0].id
  route_table_id = aws_route_table.nat[0].id
}

resource "aws_eip" "nat" {
  count = var.internet_egress_enabled ? 1 : 0

  domain = "vpc"

  tags = {
    Name = "${var.name_prefix}${local.suffix}-client-nat-eip-${var.region_key}"
  }

  depends_on = [aws_internet_gateway.this]
}

resource "aws_nat_gateway" "this" {
  count = var.internet_egress_enabled ? 1 : 0

  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.nat[0].id

  tags = {
    Name = "${var.name_prefix}${local.suffix}-client-nat-${var.region_key}"
  }

  depends_on = [aws_internet_gateway.this]
}

# Default route for the private subnets. The hub prefixes have more specific
# /16 routes pointing at the Transit Gateway, so Atlas traffic is never a
# candidate for this route - longest prefix always wins.
resource "aws_route" "private_default" {
  count = var.internet_egress_enabled ? 1 : 0

  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[0].id
}

resource "aws_ec2_transit_gateway_vpc_attachment" "this" {
  transit_gateway_id = var.transit_gateway_id
  vpc_id             = aws_vpc.this.id
  subnet_ids         = [for subnet in aws_subnet.private : subnet.id]

  dns_support            = "enable"
  ipv6_support           = "disable"
  appliance_mode_support = "disable"

  # Owned by the Transit Gateway's account. Setting these on a RAM-shared
  # gateway is not permitted and cannot be drift-detected, so they are left
  # unset and the hub account associates the attachment explicitly.
  transit_gateway_default_route_table_association = var.tgw_cross_account ? null : false
  transit_gateway_default_route_table_propagation = var.tgw_cross_account ? null : false

  tags = {
    Name = "${var.name_prefix}${local.suffix}-client-attach-${var.region_key}"
  }
}

# ── Security groups ────────────────────────────────────────────────────────────

resource "aws_security_group" "instance" {
  name        = "${var.name_prefix}${local.suffix}-client-vm-sg-${var.region_key}"
  description = "Test VM - no inbound, egress only to Atlas endpoints and AWS service endpoints"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}${local.suffix}-client-vm-sg-${var.region_key}"
  }
}

# No ingress rules at all. Session Manager is an outbound connection from the
# SSM agent, so the VM never needs an open port.

resource "aws_vpc_security_group_egress_rule" "instance_to_hubs" {
  for_each = toset(var.hub_cidr_blocks)

  security_group_id = aws_security_group.instance.id
  description       = "MongoDB over AWS PrivateLink to hub CIDR ${each.value}"
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 1024
  to_port           = 65535
}

# Package installation only. Deliberately 80/443 and nothing else: Atlas serves
# the MongoDB wire protocol on 27017 and on the 1024+ private-endpoint ports,
# none of which are allowed towards 0.0.0.0/0. That is what keeps "Atlas is
# reachable only over PrivateLink" true while the VM has internet egress.
resource "aws_vpc_security_group_egress_rule" "instance_http" {
  count = var.internet_egress_enabled ? 1 : 0

  security_group_id = aws_security_group.instance.id
  description       = "HTTP to package repositories (mongosh install)"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_egress_rule" "instance_https" {
  count = var.internet_egress_enabled ? 1 : 0

  security_group_id = aws_security_group.instance.id
  description       = "HTTPS to package repositories (mongosh install)"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "instance_to_ssm_endpoints" {
  security_group_id            = aws_security_group.instance.id
  description                  = "HTTPS to the SSM interface endpoints in this VPC"
  referenced_security_group_id = aws_security_group.vpc_endpoints.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
}

resource "aws_vpc_security_group_egress_rule" "instance_to_s3" {
  security_group_id = aws_security_group.instance.id
  description       = "HTTPS to S3 over the gateway endpoint (package repos, optional mongosh tarball)"
  prefix_list_id    = aws_vpc_endpoint.s3.prefix_list_id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_security_group" "vpc_endpoints" {
  name        = "${var.name_prefix}${local.suffix}-client-ep-sg-${var.region_key}"
  description = "SSM interface endpoints in the client VPC"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}${local.suffix}-client-ep-sg-${var.region_key}"
  }
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_from_instance" {
  security_group_id            = aws_security_group.vpc_endpoints.id
  description                  = "HTTPS from the test VM"
  referenced_security_group_id = aws_security_group.instance.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
}

# ── AWS service endpoints (not Atlas) ──────────────────────────────────────────

resource "aws_vpc_endpoint" "ssm" {
  for_each = local.ssm_services

  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [for subnet in aws_subnet.private : subnet.id]
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = {
    Name = "${var.name_prefix}${local.suffix}-client-${each.value}-ep-${var.region_key}"
  }
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = {
    Name = "${var.name_prefix}${local.suffix}-client-s3-ep-${var.region_key}"
  }
}

# ── Instance role: Session Manager only ────────────────────────────────────────

data "aws_iam_policy_document" "assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "instance" {
  name               = "${var.name_prefix}${local.suffix}-client-vm-${var.region_key}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json

  tags = {
    Name = "${var.name_prefix}${local.suffix}-client-vm-${var.region_key}"
  }
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "mongosh_object" {
  count = local.mongosh_enabled ? 1 : 0

  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${local.mongosh_bucket}/${local.mongosh_key}"]
  }
}

resource "aws_iam_role_policy" "mongosh_object" {
  count = local.mongosh_enabled ? 1 : 0

  name   = "${var.name_prefix}${local.suffix}-mongosh-read-${var.region_key}"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.mongosh_object[0].json
}

resource "aws_iam_instance_profile" "instance" {
  name = "${var.name_prefix}${local.suffix}-client-vm-${var.region_key}"
  role = aws_iam_role.instance.name

  tags = {
    Name = "${var.name_prefix}${local.suffix}-client-vm-${var.region_key}"
  }
}

# ── Test VM ────────────────────────────────────────────────────────────────────

resource "aws_instance" "test" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.private[local.first_subnet_key].id
  vpc_security_group_ids = [aws_security_group.instance.id]
  iam_instance_profile   = aws_iam_instance_profile.instance.name

  # No public IP, no key pair, no SSH. Session Manager only.
  associate_public_ip_address = false

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 8
    encrypted             = true
    delete_on_termination = true
  }

  # Carries only AWS-generated endpoint hostnames, port numbers and the test
  # scripts. No Atlas SRV URI, no credentials: those are typed into the SSM
  # session at test time and never persisted here or in Terraform state.
  user_data_base64            = local.user_data_encoded
  user_data_replace_on_change = true

  tags = {
    Name = "${var.name_prefix}${local.suffix}-test-vm-${var.region_key}"
    Role = "atlas-privatelink-test-client"
  }

  # Fail at plan time rather than after the networking has been built: EC2
  # rejects user data over 16 KB, and this bootstrap is close enough to that
  # limit that adding another script could cross it.
  lifecycle {
    precondition {
      condition     = length(local.user_data_encoded) <= local.user_data_max_bytes
      error_message = "Rendered user data is ${length(local.user_data_encoded)} bytes gzipped and base64-encoded, over the ${local.user_data_max_bytes} byte EC2 limit (raw: ${length(local.user_data_raw)} bytes). Trim a script in modules/client-vpc/templates/, or move the bulk of it to S3 and fetch it at boot over the gateway endpoint."
    }
  }

  # The boot-time mongosh install needs the egress path and the endpoints to
  # exist first, otherwise it quietly falls back to "install it later".
  depends_on = [
    aws_route.private_default,
    aws_route.to_hubs,
    aws_vpc_endpoint.s3,
    aws_vpc_endpoint.ssm,
  ]
}
