output "rds_endpoint" {
  description = "PostgreSQL endpoint (private). Seed from inside the VPC or via local_ingress_cidr."
  value       = aws_db_instance.this.address
}

output "demo_vpc_id" {
  description = "Demo VPC id — the target for the Atlas outbound peering form."
  value       = aws_vpc.this.id
}

output "demo_vpc_cidr" {
  description = "Demo VPC CIDR — enter this in the Atlas outbound-peering form."
  value       = aws_vpc.this.cidr_block
}

output "msk_bootstrap_brokers_sasl_scram" {
  description = "SASL/SCRAM bootstrap string — paste into the ASP Kafka connection (network access: VPC Peering)."
  value       = aws_msk_cluster.this.bootstrap_brokers_sasl_scram
  sensitive   = true
}

output "msk_cluster_arn" {
  value = aws_msk_cluster.this.arn
}

output "dms_replication_task_arn" {
  value = aws_dms_replication_task.cdc.replication_task_arn
}

output "kafka_topic" {
  value = var.kafka_topic
}

output "kafka_scram_secret_arn" {
  description = "Secrets Manager secret holding the MSK SCRAM credentials (value is sensitive; do not print)."
  value       = aws_secretsmanager_secret.kafka_scram.arn
}

output "vpc_peering_id" {
  description = "Atlas-initiated VPC peering id managed/accepted by this stack (null until atlas_peering_id is set)."
  value       = var.atlas_peering_id != "" ? var.atlas_peering_id : null
}
