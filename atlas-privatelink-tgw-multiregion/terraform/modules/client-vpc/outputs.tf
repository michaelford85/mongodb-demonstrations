output "vpc_id" {
  description = "ID of the client VPC."
  value       = aws_vpc.this.id
}

output "vpc_cidr_block" {
  description = "CIDR block of the client VPC."
  value       = aws_vpc.this.cidr_block
}

output "subnet_ids" {
  description = "IDs of the private subnets in the client VPC."
  value       = [for subnet in aws_subnet.private : subnet.id]
}

output "route_table_id" {
  description = "ID of the client VPC route table."
  value       = aws_route_table.private.id
}

output "transit_gateway_attachment_id" {
  description = "ID of the client VPC's Transit Gateway attachment."
  value       = aws_ec2_transit_gateway_vpc_attachment.this.id
}

output "instance_id" {
  description = "Instance ID of the test VM."
  value       = aws_instance.test.id
}

output "instance_private_ip" {
  description = "Private IPv4 address of the test VM. There is no public address."
  value       = aws_instance.test.private_ip
}

output "instance_security_group_id" {
  description = "ID of the test VM's security group."
  value       = aws_security_group.instance.id
}

output "internet_egress_enabled" {
  description = "Whether the NAT egress path exists. The test VM never has a public IP either way."
  value       = var.internet_egress_enabled
}

output "nat_gateway_public_ip" {
  description = "Elastic IP of the NAT gateway - the only public IP in the lab, outbound only. Null when internet egress is disabled."
  value       = var.internet_egress_enabled ? aws_eip.nat[0].public_ip : null
}

output "instance_role_name" {
  description = "Name of the IAM role attached to the test VM."
  value       = aws_iam_role.instance.name
}
