variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "region_key" {
  description = "Short region key (a, b, c) this Transit Gateway belongs to."
  type        = string
}

variable "amazon_side_asn" {
  description = "BGP ASN for the Amazon side of the Transit Gateway."
  type        = number
}
