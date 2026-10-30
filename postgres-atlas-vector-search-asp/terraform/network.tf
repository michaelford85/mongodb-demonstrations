# ─── Networking ────────────────────────────────────────────────────────
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "${var.resource_prefix}-vpc" }
}

resource "aws_subnet" "a" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, 0)
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = false

  tags = { Name = "${var.resource_prefix}-private-a" }
}

resource "aws_subnet" "b" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, 1)
  availability_zone       = "${var.aws_region}b"
  map_public_ip_on_launch = false

  tags = { Name = "${var.resource_prefix}-private-b" }
}

resource "aws_route_table" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.resource_prefix}-rt" }
}

resource "aws_route_table_association" "a" {
  subnet_id      = aws_subnet.a.id
  route_table_id = aws_route_table.this.id
}

resource "aws_route_table_association" "b" {
  subnet_id      = aws_subnet.b.id
  route_table_id = aws_route_table.this.id
}

# ─── Security groups ───────────────────────────────────────────────────
resource "aws_security_group" "rds" {
  name   = "${var.resource_prefix}-rds"
  vpc_id = aws_vpc.this.id

  tags = { Name = "${var.resource_prefix}-rds" }
}

resource "aws_security_group" "msk" {
  name   = "${var.resource_prefix}-msk"
  vpc_id = aws_vpc.this.id

  tags = { Name = "${var.resource_prefix}-msk" }
}

resource "aws_security_group" "dms" {
  name   = "${var.resource_prefix}-dms"
  vpc_id = aws_vpc.this.id

  tags = { Name = "${var.resource_prefix}-dms" }
}

# DMS replication instance → PostgreSQL
resource "aws_security_group_rule" "rds_from_dms" {
  type                     = "ingress"
  security_group_id        = aws_security_group.rds.id
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.dms.id
}

# Internet Gateway — controlled explicitly by enable_igw. Needed for the
# laptop seeding path (with local_ingress_cidr + rds_publicly_accessible);
# the stack is fully private when disabled.
resource "aws_internet_gateway" "this" {
  count = var.enable_igw ? 1 : 0

  # Without vpc_id the gateway is created but never ATTACHED, and the default
  # route / publicly accessible RDS fail with "different networks" /
  # "no internet gateway attached".
  vpc_id = aws_vpc.this.id

  tags = { Name = "${var.resource_prefix}-igw" }
}

# Let the IGW attachment propagate to the RDS/EC2 APIs before dependents.
resource "time_sleep" "igw_settle" {
  count = var.enable_igw ? 1 : 0

  create_duration = "30s"

  depends_on = [aws_internet_gateway.this]
}

resource "aws_route" "default_via_igw" {
  count = var.enable_igw ? 1 : 0

  route_table_id         = aws_route_table.this.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this[0].id

  depends_on = [time_sleep.igw_settle]
}

# Optional local access for seeding: SG allows the given /32 only.
resource "aws_security_group_rule" "rds_from_local" {
  count             = var.local_ingress_cidr != "" ? 1 : 0
  type              = "ingress"
  security_group_id = aws_security_group.rds.id
  from_port         = 5432
  to_port           = 5432
  protocol          = "tcp"
  cidr_blocks       = [var.local_ingress_cidr]
}

# DMS → MSK on the SASL/SCRAM + TLS listener (9096)
resource "aws_security_group_rule" "msk_from_dms" {
  type                     = "ingress"
  security_group_id        = aws_security_group.msk.id
  from_port                = 9096
  to_port                  = 9096
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.dms.id
}

# Atlas VPC (peered) → MSK on 9096, so Atlas Stream Processing can consume.
resource "aws_security_group_rule" "msk_from_atlas" {
  count             = var.atlas_cidr != "" ? 1 : 0
  type              = "ingress"
  security_group_id = aws_security_group.msk.id
  from_port         = 9096
  to_port           = 9096
  protocol          = "tcp"
  cidr_blocks       = [var.atlas_cidr]
}

resource "aws_security_group_rule" "dms_egress" {
  type              = "egress"
  security_group_id = aws_security_group.dms.id
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
}

# Atlas-initiated peering: Atlas created the connection from its side
# ("Add outbound connection", status "Waiting for Approval"). Terraform
# accepts it on the AWS side and wires the demo route + MSK firewall.
resource "aws_vpc_peering_connection_accepter" "atlas" {
  count = var.atlas_peering_id != "" ? 1 : 0

  vpc_peering_connection_id = var.atlas_peering_id
  auto_accept               = true
}

resource "aws_route" "demo_to_atlas" {
  count = var.atlas_peering_id != "" ? 1 : 0

  route_table_id            = aws_route_table.this.id
  destination_cidr_block    = var.atlas_cidr
  vpc_peering_connection_id = var.atlas_peering_id
}

# The Atlas side already routes to the demo VPC CIDR (it was entered in the
# Atlas outbound-peering form), so no Atlas-side route work is needed.
