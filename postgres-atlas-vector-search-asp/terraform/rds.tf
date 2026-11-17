# ─── RDS PostgreSQL source (CDC-enabled) ───────────────────────────────
resource "aws_db_subnet_group" "this" {
  name       = "${var.resource_prefix}-pg"
  subnet_ids = [aws_subnet.a.id, aws_subnet.b.id]

  tags = { Name = "${var.resource_prefix}-pg" }
}

resource "aws_db_parameter_group" "this" {
  name   = "${var.resource_prefix}-pg-params"
  family = "postgres16"

  # Required for PostgreSQL logical replication (DMS CDC).
  parameter {
    name         = "rds.logical_replication"
    value        = "1"
    apply_method = "pending-reboot"
  }

  parameter {
    name         = "max_replication_slots"
    value        = "5"
    apply_method = "pending-reboot"
  }

  parameter {
    name         = "max_wal_senders"
    value        = "10"
    apply_method = "pending-reboot"
  }

  parameter {
    name         = "wal_sender_timeout"
    value        = "0"
    apply_method = "pending-reboot"
  }
}

resource "aws_db_instance" "this" {
  identifier     = "${var.resource_prefix}-pg"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  db_name               = var.db_name
  username              = var.db_admin_username
  password              = var.db_admin_password
  port                  = 5432
  allocated_storage     = 20
  max_allocated_storage = 50

  db_subnet_group_name   = aws_db_subnet_group.this.name
  parameter_group_name   = aws_db_parameter_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  # Only set true together with local_ingress_cidr — network.tf provisions
  # the internet gateway (with a settle delay) this requires.
  publicly_accessible = var.rds_publicly_accessible

  # A publicly accessible instance requires the VPC's IGW attachment to be
  # fully propagated; wait for it.
  depends_on = [time_sleep.igw_settle]

  multi_az                = false
  backup_retention_period = 1
  skip_final_snapshot     = true
  deletion_protection     = false

  tags = { Name = "${var.resource_prefix}-pg" }
}

# Least-privilege role for DMS CDC. Created by seed_postgres.py together
# with the schema (needs RDS master privileges the Terraform postgresql
# provider cannot assume here).
# See scripts/seed_postgres.py --provision-cdc-user.
