# ─── Amazon MSK (private, SASL/SCRAM + TLS) ────────────────────────────
# DMS Kafka targets do not support IAM access control for MSK, so this
# cluster uses SASL/SCRAM with TLS (listener 9096). MSK stores SCRAM
# credentials in AWS Secrets Manager. SASL/SCRAM clusters cannot be made
# publicly accessible — all consumers (DMS, Atlas Stream Processing) must
# connect privately, which is what we want.

resource "random_password" "kafka_scram" {
  length  = 24
  special = false
}

# MSK SCRAM secret association REQUIRES a customer-managed KMS key; the
# default Secrets Manager encryption key is rejected by Amazon MSK.
resource "aws_kms_key" "msk_scram" {
  description             = "${var.resource_prefix} MSK SCRAM secret encryption"
  deletion_window_in_days = 7
}

resource "aws_secretsmanager_secret" "kafka_scram" {
  name                    = "AmazonMSK_${var.resource_prefix}"
  description             = "SASL/SCRAM credentials for the ${var.resource_prefix} MSK cluster"
  kms_key_id              = aws_kms_key.msk_scram.arn
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "kafka_scram" {
  secret_id = aws_secretsmanager_secret.kafka_scram.id
  secret_string = jsonencode({
    username = "demo_kafka_user"
    password = random_password.kafka_scram.result
  })
}

# MSK discovers SCRAM credentials via a tags-based association.
resource "aws_msk_scram_secret_association" "this" {
  cluster_arn     = aws_msk_cluster.this.arn
  secret_arn_list = [aws_secretsmanager_secret.kafka_scram.arn]
}

resource "aws_msk_configuration" "this" {
  name              = "${var.resource_prefix}-config"
  kafka_versions    = [var.msk_kafka_version]
  server_properties = <<PROPS
auto.create.topics.enable=true
log.retention.hours=24
PROPS
}

resource "aws_msk_cluster" "this" {
  cluster_name           = "${var.resource_prefix}-msk"
  kafka_version          = var.msk_kafka_version
  number_of_broker_nodes = var.msk_broker_count

  broker_node_group_info {
    instance_type   = var.msk_instance_type
    client_subnets  = [aws_subnet.a.id, aws_subnet.b.id]
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info {
        volume_size = 10
      }
    }

    connectivity_info {
      # Intentionally no public access: SASL/SCRAM clusters cannot be public.
    }
  }

  client_authentication {
    sasl {
      scram = true
    }
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.this.arn
    revision = aws_msk_configuration.this.latest_revision
  }

  # Dev sizing: single-node storage, short retention, no MSK-level backup.
  tags = { Name = "${var.resource_prefix}-msk" }
}
