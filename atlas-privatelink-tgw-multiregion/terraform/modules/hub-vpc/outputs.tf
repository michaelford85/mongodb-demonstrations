output "vpc_id" {
  description = "ID of the hub VPC."
  value       = aws_vpc.this.id
}

output "vpc_cidr_block" {
  description = "CIDR block of the hub VPC."
  value       = aws_vpc.this.cidr_block
}

output "subnet_ids" {
  description = "IDs of the endpoint subnets, one per Availability Zone."
  value       = [for subnet in aws_subnet.endpoints : subnet.id]
}

output "availability_zones" {
  description = "Availability Zones the endpoint ENIs are spread across."
  value       = sort([for subnet in aws_subnet.endpoints : subnet.availability_zone])
}

output "route_table_id" {
  description = "ID of the hub VPC route table."
  value       = aws_route_table.this.id
}

output "security_group_id" {
  description = "ID of the security group attached to the interface endpoint ENIs."
  value       = aws_security_group.endpoints.id
}

output "transit_gateway_attachment_id" {
  description = "ID of the hub VPC's Transit Gateway attachment."
  value       = aws_ec2_transit_gateway_vpc_attachment.this.id
}

output "endpoint_ids" {
  description = "Map of endpoint label => interface VPC endpoint ID."
  value       = { for label, endpoint in aws_vpc_endpoint.atlas : label => endpoint.id }
}

output "endpoint_dns_names" {
  description = "Map of endpoint label => DNS names generated for the interface endpoint. These are what the Atlas private-endpoint-aware connection string resolves to; they are not secret."
  value = {
    for label, endpoint in aws_vpc_endpoint.atlas :
    label => [for entry in endpoint.dns_entry : entry.dns_name]
  }
}

output "endpoint_regional_dns_names" {
  description = "Map of endpoint label => the regional (non zonal) DNS name of the interface endpoint."
  value = {
    for label, endpoint in aws_vpc_endpoint.atlas :
    label => tolist(endpoint.dns_entry)[0].dns_name
  }
}
