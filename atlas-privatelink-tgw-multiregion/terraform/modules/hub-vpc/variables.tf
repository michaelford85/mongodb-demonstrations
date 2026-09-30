variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "region_key" {
  description = "Short region key (a, b, c) this hub belongs to."
  type        = string
}

variable "vpc_cidr_block" {
  description = "CIDR block of the hub VPC."
  type        = string
}

variable "subnet_cidrs" {
  description = "Subnets that hold the interface endpoint ENIs and the Transit Gateway attachment. One per Availability Zone."
  type        = list(string)
}

variable "availability_zones" {
  description = "Explicit AZ names, positionally matched to subnet_cidrs. Empty means the first N available AZs in the region."
  type        = list(string)
  default     = []
}

variable "atlas_endpoint_services" {
  description = "Map of label => existing Atlas private endpoint service name to create an interface endpoint for."
  type        = map(string)
}

variable "client_cidr_blocks" {
  description = "CIDRs of the client VPC(s) allowed to reach the endpoint ENIs, including any that arrive over inter-region Transit Gateway peering. Used for both the security group rules and the return routes."
  type        = list(string)
}

variable "transit_gateway_id" {
  description = "ID of the Transit Gateway in this region to attach the hub VPC to."
  type        = string
}
