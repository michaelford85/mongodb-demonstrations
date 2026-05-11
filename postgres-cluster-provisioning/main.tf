# Look up the default VPC and its subnets. Using the account's default VPC
# keeps this demo self-contained: no extra networking resources are created
# and teardown is a single `terraform destroy`.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# DB subnet group spans the default VPC's subnets so Aurora can place the
# writer (and any future readers) across multiple AZs.
resource "aws_db_subnet_group" "this" {
  name        = "${var.cluster_identifier}-subnet-group"
  description = "Subnet group for ${var.cluster_identifier}"
  subnet_ids  = data.aws_subnets.default.ids
}

# Security group: only the explicitly allow-listed CIDR blocks can reach 5432.
resource "aws_security_group" "db" {
  name        = "${var.cluster_identifier}-sg"
  description = "Allow PostgreSQL access to ${var.cluster_identifier}"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "PostgreSQL from allow-listed networks"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  egress {
    description = "All egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Aurora PostgreSQL cluster. pgvector is available as a regular extension from
# Aurora PostgreSQL 15.3 onwards and can be enabled with `CREATE EXTENSION
# vector;` once you connect.
resource "aws_rds_cluster" "this" {
  cluster_identifier      = var.cluster_identifier
  engine                  = "aurora-postgresql"
  engine_version          = var.engine_version
  database_name           = var.db_name
  master_username         = var.db_admin_username
  master_password         = var.db_admin_password
  port                    = 5432
  db_subnet_group_name    = aws_db_subnet_group.this.name
  vpc_security_group_ids  = [aws_security_group.db.id]
  storage_encrypted       = true
  backup_retention_period = var.backup_retention_days
  # Demo-friendly destroy semantics; production should set this to false and
  # provide a final snapshot identifier.
  skip_final_snapshot = true
  apply_immediately   = true
}

resource "aws_rds_cluster_instance" "this" {
  identifier           = "${var.cluster_identifier}-instance-1"
  cluster_identifier   = aws_rds_cluster.this.id
  engine               = aws_rds_cluster.this.engine
  engine_version       = aws_rds_cluster.this.engine_version
  instance_class       = var.instance_class
  db_subnet_group_name = aws_db_subnet_group.this.name
  publicly_accessible  = var.publicly_accessible
}
