output "transit_gateway_id" {
  description = "ID of the regional Transit Gateway."
  value       = aws_ec2_transit_gateway.this.id
}

output "transit_gateway_arn" {
  description = "ARN of the regional Transit Gateway."
  value       = aws_ec2_transit_gateway.this.arn
}

output "transit_gateway_route_table_id" {
  description = "ID of the lab's explicit Transit Gateway route table."
  value       = aws_ec2_transit_gateway_route_table.this.id
}

output "amazon_side_asn" {
  description = "ASN assigned to the Amazon side of the Transit Gateway."
  value       = aws_ec2_transit_gateway.this.amazon_side_asn
}
