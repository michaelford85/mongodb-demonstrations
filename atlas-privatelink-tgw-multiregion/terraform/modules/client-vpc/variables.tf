variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "region_key" {
  description = "Short region key (a, b, c) the client VPC lives in."
  type        = string
}

variable "name_suffix" {
  description = "Extra label appended to resource names, e.g. \"spoke-1\". Lets the same module build the hub account's own client VPC and an application account's spoke VPC without ambiguous names in the console."
  type        = string
  default     = ""
}

variable "tgw_cross_account" {
  description = "True when the Transit Gateway belongs to another account and was shared through RAM. The default route table association and propagation flags are then left unset: they belong to the gateway's owner, which accepts the attachment and associates it explicitly."
  type        = bool
  default     = false
}

variable "vpc_cidr_block" {
  description = "CIDR block of the client VPC."
  type        = string
}

variable "subnet_cidrs" {
  description = "Private subnets for the test VM, the SSM interface endpoints and the Transit Gateway attachment."
  type        = list(string)
}

variable "availability_zones" {
  description = "Explicit AZ names, positionally matched to subnet_cidrs. Empty means the first N available AZs in the region."
  type        = list(string)
  default     = []
}

variable "instance_type" {
  description = "EC2 instance type for the test VM. Must be an x86_64 type: the AMI lookup pins Amazon Linux 2023 x86_64."
  type        = string
  default     = "t3.micro"
}

variable "transit_gateway_id" {
  description = "ID of the Transit Gateway in this region to attach the client VPC to."
  type        = string
}

variable "internet_egress_enabled" {
  description = "Create an internet gateway, a NAT subnet and a NAT gateway so the test VM can install mongosh from repo.mongodb.org. The VM itself never gets a public IP and never accepts inbound traffic. MongoDB wire-protocol ports stay restricted to the hub CIDRs, so Atlas cannot be reached over this path."
  type        = bool
  default     = true
}

variable "nat_subnet_cidr" {
  description = "CIDR of the small public subnet that holds the NAT gateway. Required when internet_egress_enabled is true. Nothing else is ever placed in it."
  type        = string
  default     = ""
}

variable "hub_cidr_blocks" {
  description = "CIDRs of every hub VPC in the lab, local and remote. Routed explicitly through the Transit Gateway and allowed out of the test VM's security group."
  type        = list(string)
}

variable "endpoint_targets" {
  description = "Interface endpoint DNS names the on-instance test script probes, one entry per hub endpoint. Not secret: these are AWS-generated endpoint hostnames, not an Atlas connection string."
  type = list(object({
    region_key   = string
    aws_region   = string
    label        = string
    dns_name     = string
    hub_cidr     = string
    cross_region = bool
  }))
}

variable "test_ports" {
  description = "Extra TCP ports the on-instance test script probes, beyond the scan range."
  type        = list(number)
}

variable "test_port_scan_range" {
  description = "Inclusive port range scanned on each endpoint ENI."
  type = object({
    start = number
    end   = number
  })
}

variable "mongosh_s3_uri" {
  description = "Optional s3:// URI of a mongosh tarball to install over the S3 gateway endpoint. Empty disables the mongosh install."
  type        = string
  default     = ""
}
