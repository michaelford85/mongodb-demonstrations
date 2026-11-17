# ─── IAM roles required by DMS ─────────────────────────────────────────
# AWS DMS looks up these service-linked role names by their EXACT names in
# the account ("dms-vpc-role", "dms-cloudwatch-logs-role"). Suffixes are not
# permitted. If your account already has them (any prior DMS usage), set
# create_dms_service_roles = false in terraform.tfvars.

variable "create_dms_service_roles" {
  type        = bool
  default     = true
  description = "Set false if dms-vpc-role / dms-cloudwatch-logs-role already exist in the account."
}

data "aws_iam_policy_document" "dms_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["dms.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "dms_vpc" {
  count = var.create_dms_service_roles ? 1 : 0

  name               = "dms-vpc-role"
  assume_role_policy = data.aws_iam_policy_document.dms_assume.json
}

resource "aws_iam_role_policy_attachment" "dms_vpc" {
  count = var.create_dms_service_roles ? 1 : 0

  role       = aws_iam_role.dms_vpc[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonDMSVPCManagementRole"
}

resource "aws_iam_role" "dms_cloudwatch" {
  count = var.create_dms_service_roles ? 1 : 0

  name               = "dms-cloudwatch-logs-role"
  assume_role_policy = data.aws_iam_policy_document.dms_assume.json
}

resource "aws_iam_role_policy_attachment" "dms_cloudwatch" {
  count = var.create_dms_service_roles ? 1 : 0

  role       = aws_iam_role.dms_cloudwatch[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonDMSCloudWatchLogsRole"
}

# ─── DMS replication instance + endpoints + task ───────────────────────
resource "aws_dms_replication_subnet_group" "this" {
  replication_subnet_group_id          = "${var.resource_prefix}-dms-subnets"
  replication_subnet_group_description = "${var.resource_prefix} DMS subnet group"
  subnet_ids                           = [aws_subnet.a.id, aws_subnet.b.id]

  depends_on = [aws_iam_role.dms_vpc]
}

resource "aws_dms_replication_instance" "this" {
  replication_instance_id     = "${var.resource_prefix}-dms"
  replication_instance_class  = var.dms_instance_class
  allocated_storage           = 20
  publicly_accessible         = false
  multi_az                    = false
  auto_minor_version_upgrade  = true
  vpc_security_group_ids      = [aws_security_group.dms.id]
  replication_subnet_group_id = aws_dms_replication_subnet_group.this.id

  depends_on = [aws_iam_role.dms_vpc]
}

resource "aws_dms_endpoint" "source_pg" {
  database_name = var.db_name
  endpoint_id   = "${var.resource_prefix}-source-pg"
  endpoint_type = "source"
  engine_name   = "postgres"

  server_name = aws_db_instance.this.address
  port        = 5432
  username    = var.db_admin_username
  password    = var.db_admin_password

  ssl_mode = "require"

  # DMS CDC uses a logical decoding slot; test_decoding is available on RDS
  # out of the box (pglogical would require adding it to shared_preload_libraries).
  postgres_settings {
    plugin_name = "test_decoding"
  }
}

resource "aws_dms_endpoint" "target_msk" {
  endpoint_id   = "${var.resource_prefix}-target-msk"
  endpoint_type = "target"
  engine_name   = "kafka"

  kafka_settings {
    broker = aws_msk_cluster.this.bootstrap_brokers_sasl_scram

    topic             = var.kafka_topic
    message_format    = "json-unformatted"
    message_max_bytes = 1000000

    # SASL/SCRAM + TLS — the only supported auth for a DMS→MSK target.
    security_protocol = "sasl-ssl"
    sasl_username     = jsondecode(aws_secretsmanager_secret_version.kafka_scram.secret_string)["username"]
    sasl_password     = jsondecode(aws_secretsmanager_secret_version.kafka_scram.secret_string)["password"]

    # Add operation/timestamp metadata to every record so ASP can
    # distinguish load/insert/update/delete.
    include_transaction_details = true
    include_null_and_empty      = true
  }

  depends_on = [aws_msk_cluster.this]
}

# Table mappings: one topic, partition by primary key so updates for the
# same row land in order on a single partition.
resource "aws_dms_replication_task" "cdc" {
  replication_task_id      = "${var.resource_prefix}-cdc"
  migration_type           = "full-load-and-cdc"
  replication_instance_arn = aws_dms_replication_instance.this.replication_instance_arn
  source_endpoint_arn      = aws_dms_endpoint.source_pg.endpoint_arn
  target_endpoint_arn      = aws_dms_endpoint.target_msk.endpoint_arn

  table_mappings = jsonencode({
    rules = [
      {
        rule-type = "selection"
        rule-id   = "1"
        rule-name = "include-knowledge-items"
        object-locator = {
          schema-name = "demo_schema"
          table-name  = "knowledge_items"
        }
        rule-action = "include"
      }
    ]
  })

  # No object-mapping rule: with default table mapping, CDC records for a
  # single table use "schema.table" as the partition key, so all events for
  # knowledge_items land on one partition in source order. An object-mapping
  # rule with partition-key-type "attribute-name" would require full
  # attribute-mappings, which the demo does not need.

  replication_task_settings = jsonencode({
    Logging = {
      EnableLogging = true
    }
    FullLoadSettings = {
      MaxFullLoadSubTasks = 2
      CommitRate          = 1000
    }
    TargetMetadata = {
      IncludeOpForFullLoad = true
      FullLoadErrorHandling = {
        MaxErrorArray = 100
      }
    }
    ControlledTaskSettings = {}
    ErrorHandling = {
      DataErrorPolicy = "LOG_IT"
    }
  })

  start_replication_task = false

  depends_on = [aws_iam_role.dms_cloudwatch]
}
