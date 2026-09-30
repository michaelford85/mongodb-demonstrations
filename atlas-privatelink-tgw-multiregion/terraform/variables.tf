# ── Naming and mandatory tags ──────────────────────────────────────────────────

variable "name_prefix" {
  description = "Prefix applied to the name of every resource this lab creates. Keep it short: AWS name tags and security group names are derived from it."
  type        = string
  default     = "atlas-plink-tgw"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,22}$", var.name_prefix))
    error_message = "name_prefix must be 2-23 characters, lowercase alphanumeric or hyphen, and start with a letter or digit."
  }
}

variable "tag_project" {
  description = "Value for the mandatory Project tag."
  type        = string
  default     = "mongodb-demonstrations"

  validation {
    condition     = trimspace(var.tag_project) != ""
    error_message = "tag_project must not be empty."
  }
}

variable "tag_environment" {
  description = "Value for the mandatory Environment tag. This lab is disposable, so something like lab, sandbox or dev is appropriate."
  type        = string
  default     = "lab"

  validation {
    condition     = trimspace(var.tag_environment) != ""
    error_message = "tag_environment must not be empty."
  }
}

variable "tag_owner" {
  description = "Value for the mandatory Owner tag. Whoever is accountable for deleting this lab. No default on purpose."
  type        = string

  validation {
    condition     = trimspace(var.tag_owner) != ""
    error_message = "tag_owner must not be empty - every resource in this lab has to be attributable to someone."
  }
}

variable "tag_purpose" {
  description = "Value for the mandatory Purpose tag."
  type        = string
  default     = "atlas-privatelink-tgw-multiregion-demo"

  validation {
    condition     = trimspace(var.tag_purpose) != ""
    error_message = "tag_purpose must not be empty."
  }
}

variable "extra_tags" {
  description = "Optional additional tags merged on top of the mandatory ones. Cannot be used to unset a mandatory tag."
  type        = map(string)
  default     = {}
}

# ── Regions / hubs ─────────────────────────────────────────────────────────────

variable "hubs" {
  description = <<-EOT
    One entry per lab region, keyed by a short region key ("a", "b", and
    optionally "c"). Each entry describes the hub VPC that holds the AWS
    interface endpoints pointing at that region's *existing* Atlas private
    endpoint service.

    Fields:
      aws_region              AWS region name, e.g. eu-west-1.
      vpc_cidr_block          CIDR of the hub VPC. Must not overlap any other
                              VPC in this lab.
      subnet_cidrs            Subnets that will hold the interface endpoint
                              ENIs. Supply two or more, in different AZs, so
                              the endpoint survives an AZ failure. One ENI per
                              subnet is billed per hour.
      availability_zones      Optional explicit AZ names, positionally matched
                              to subnet_cidrs. Empty means "use the first N
                              available AZs in the region".
      atlas_endpoint_services Map of label => Atlas endpoint service name
                              (com.amazonaws.vpce.<region>.vpce-svc-xxxxxxxx).
                              One Atlas project-region endpoint service serves
                              every cluster in that Atlas project and region;
                              add a second entry only for a second Atlas
                              project in the same region.
      amazon_side_asn         Optional Transit Gateway ASN. Defaults to
                              64512 + position, which keeps peered gateways on
                              distinct ASNs.
  EOT

  type = map(object({
    aws_region              = string
    vpc_cidr_block          = string
    subnet_cidrs            = list(string)
    availability_zones      = optional(list(string), [])
    atlas_endpoint_services = map(string)
    amazon_side_asn         = optional(number)
  }))

  # No default: the Atlas endpoint service names are specific to your Atlas
  # project and regions, and there is no safe placeholder for them. See
  # .env.example for a ready-to-edit HUBS value.

  validation {
    condition     = length(setsubtract(["a", "b"], keys(var.hubs))) == 0
    error_message = "hubs must contain at least the region keys \"a\" and \"b\"."
  }

  validation {
    condition     = length(setsubtract(keys(var.hubs), ["a", "b", "c"])) == 0
    error_message = "hubs keys must be drawn from \"a\", \"b\", \"c\". Each key needs a matching aliased provider in providers.tf and a matching set of blocks in main.tf."
  }

  validation {
    condition     = length(distinct([for h in var.hubs : h.aws_region])) == length(var.hubs)
    error_message = "Each hub must live in a distinct AWS region."
  }

  validation {
    condition     = alltrue([for h in var.hubs : length(h.subnet_cidrs) >= 1])
    error_message = "Every hub needs at least one endpoint subnet."
  }

  validation {
    condition     = alltrue([for h in var.hubs : length(h.availability_zones) == 0 || length(h.availability_zones) == length(h.subnet_cidrs)])
    error_message = "availability_zones must either be empty or have exactly one AZ per entry in subnet_cidrs."
  }

  validation {
    condition     = alltrue([for h in var.hubs : length(h.atlas_endpoint_services) >= 1])
    error_message = "Every hub needs at least one Atlas endpoint service name."
  }

  validation {
    condition = alltrue([
      for h in var.hubs : alltrue([
        for name in values(h.atlas_endpoint_services) :
        can(regex("^com\\.amazonaws\\.vpce\\.[a-z0-9-]+\\.vpce-svc-[0-9a-f]+$", name))
      ])
    ])
    error_message = "Each Atlas endpoint service name must look like com.amazonaws.vpce.<region>.vpce-svc-0123456789abcdef0. Read it from the Atlas private endpoint you already created in that project and region."
  }

  validation {
    condition = alltrue([
      for h in var.hubs : alltrue([
        for name in values(h.atlas_endpoint_services) :
        split(".", name)[3] == h.aws_region
      ])
    ])
    error_message = "An Atlas endpoint service name carries the region it lives in. It must match the aws_region of the hub that targets it - an interface endpoint cannot cross regions."
  }
}

variable "allow_single_az_endpoints" {
  description = "Set true to accept hubs with a single endpoint subnet. Default false: two or more AZs per hub is the supported shape, and a single-AZ endpoint takes the whole region's Atlas path down with its AZ."
  type        = bool
  default     = false
}

# ── Client VPC and test VM ─────────────────────────────────────────────────────

variable "client" {
  description = <<-EOT
    The client/test VPC. It is created in exactly one region - the region named
    by region_key, which must be a key of `hubs`. The test VM lives here with no
    public IP, no key pair and no inbound rules; access is SSM Session Manager.

    internet_egress_enabled creates an internet gateway, a small NAT subnet and
    a NAT gateway so the VM can install mongosh. It does not open a path to
    Atlas: the VM's security group only allows the MongoDB port range towards
    the hub VPC CIDRs, and only 80/443 towards the internet. Turn it off again
    once mongosh is installed to delete the NAT gateway, its elastic IP and the
    default route - the Atlas path is unaffected either way.

    nat_subnet_cidr is required when internet_egress_enabled is true. It is
    validated against the other subnets like any other prefix.
  EOT

  type = object({
    region_key              = string
    vpc_cidr_block          = string
    subnet_cidrs            = list(string)
    availability_zones      = optional(list(string), [])
    instance_type           = optional(string, "t3.micro")
    internet_egress_enabled = optional(bool, true)
    nat_subnet_cidr         = optional(string, "")
  })

  default = {
    region_key      = "a"
    vpc_cidr_block  = "10.10.0.0/16"
    subnet_cidrs    = ["10.10.1.0/24", "10.10.2.0/24"]
    nat_subnet_cidr = "10.10.255.0/28"
  }

  validation {
    condition     = var.client.region_key == "a"
    error_message = "client.region_key must be \"a\". Region A is the client region by definition in this lab: it is the one region whose provider alias is wired to the client-vpc module. The field is explicit rather than implied so the wiring is readable, and so a future variant can move the workload without renaming every CIDR."
  }

  validation {
    condition     = length(var.client.subnet_cidrs) >= 1
    error_message = "The client VPC needs at least one subnet."
  }

  validation {
    condition     = length(var.client.availability_zones) == 0 || length(var.client.availability_zones) == length(var.client.subnet_cidrs)
    error_message = "client.availability_zones must either be empty or have exactly one AZ per entry in subnet_cidrs."
  }
}

variable "test_ports" {
  description = "Extra TCP ports the on-instance connectivity script probes, on top of test_port_scan_range. Atlas allocates a block of ports per private endpoint starting at 1024, but which block depends on how many clusters and endpoints the project already has - so the scan range matters more than this list. `atlas-plink-test --srv <hostname>` reads the real ports from DNS and needs neither."
  type        = list(number)
  default     = [27017]

  validation {
    condition     = alltrue([for p in var.test_ports : p >= 1024 && p <= 65535])
    error_message = "test_ports must be inside 1024-65535, the range the endpoint security groups open."
  }
}

variable "test_port_scan_range" {
  description = "Inclusive port range the on-instance script scans on each endpoint ENI. Atlas private endpoints start at 1024 but a project with several clusters or endpoints lands higher - 1024-1060 covers the common cases. Probes run in parallel, so a wider range costs seconds, not minutes."
  type = object({
    start = number
    end   = number
  })
  default = {
    start = 1024
    end   = 1060
  }

  validation {
    condition     = var.test_port_scan_range.start >= 1024 && var.test_port_scan_range.end <= 65535 && var.test_port_scan_range.start <= var.test_port_scan_range.end
    error_message = "test_port_scan_range must sit inside 1024-65535 with start <= end."
  }

  validation {
    condition     = var.test_port_scan_range.end - var.test_port_scan_range.start <= 255
    error_message = "test_port_scan_range must span 256 ports or fewer. Use `atlas-plink-test --srv <hostname>` instead of scanning wider - it reads the exact ports from the SRV record."
  }
}

variable "mongosh_s3_uri" {
  description = <<-EOT
    Optional s3:// URI of a mongosh tarball you have already staged in your own
    bucket, e.g. s3://my-bucket/mongosh-linux-x64.tgz. The client VPC has no
    internet egress by design (no NAT gateway, no public IPs), so this is the
    supported way to get mongosh onto the test VM: it is fetched over the S3
    gateway endpoint. Leave empty to run the TCP-only reachability test, which
    needs no packages at all.
  EOT

  type    = string
  default = ""

  validation {
    condition     = var.mongosh_s3_uri == "" || can(regex("^s3://[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]/.+$", var.mongosh_s3_uri))
    error_message = "mongosh_s3_uri must be empty or a full s3://bucket/key URI."
  }
}

# ── Application accounts (spokes) ──────────────────────────────────────────────

variable "spokes" {
  description = <<-EOT
    Application AWS accounts that consume the SAME two Atlas interface
    endpoints owned by this (hub) account. One entry per account, keyed "1" or
    "2". Leave empty for the single-account lab.

    A spoke never creates an interface endpoint and never registers anything
    with Atlas. It gets a VPC, a Transit Gateway attachment to the shared
    region-A gateway, and a test VM. That is what keeps the number of
    PrivateLink endpoints at two no matter how many accounts consume them.

    Spokes live in region A. Each reaches the region-B Atlas nodes the same way
    the hub client VPC does: region-A TGW, inter-region peering, region-B TGW.

    Fields:
      account_id      12-digit AWS account ID of the application account.
      role_arn        Role Terraform assumes in that account. In an AWS
                      Organization this is usually
                      arn:aws:iam::<account-id>:role/OrganizationAccountAccessRole.
      vpc_cidr_block  Spoke VPC CIDR. Must not overlap anything else in the lab
                      - Terraform checks every prefix across every account.
      subnet_cidrs    Private subnets for the VM and its SSM endpoints.
      nat_subnet_cidr Small public subnet for the NAT gateway, required while
                      internet_egress_enabled is true (mongosh install).
  EOT

  type = map(object({
    account_id              = string
    role_arn                = string
    vpc_cidr_block          = string
    subnet_cidrs            = list(string)
    nat_subnet_cidr         = optional(string, "")
    availability_zones      = optional(list(string), [])
    instance_type           = optional(string, "t3.micro")
    internet_egress_enabled = optional(bool, true)
  }))

  default = {}

  validation {
    condition     = length(setsubtract(keys(var.spokes), ["1", "2"])) == 0
    error_message = "spokes keys must be \"1\" or \"2\". Each needs a matching aliased provider in providers.tf and a matching module block in main.tf; see \"Adding another application account\" in README.md."
  }

  validation {
    condition     = alltrue([for s in var.spokes : can(regex("^[0-9]{12}$", s.account_id))])
    error_message = "spokes[*].account_id must be a 12-digit AWS account ID."
  }

  validation {
    condition     = alltrue([for s in var.spokes : can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:role/.+$", s.role_arn))])
    error_message = "spokes[*].role_arn must be a full IAM role ARN, e.g. arn:aws:iam::123456789012:role/OrganizationAccountAccessRole."
  }

  validation {
    condition     = alltrue([for key, s in var.spokes : split(":", s.role_arn)[4] == s.account_id])
    error_message = "spokes[*].role_arn must name a role inside that spoke's own account_id."
  }

  validation {
    condition     = length(distinct([for s in var.spokes : s.account_id])) == length(var.spokes)
    error_message = "Each spoke must be a distinct AWS account."
  }

  validation {
    condition     = alltrue([for s in var.spokes : length(s.subnet_cidrs) >= 1])
    error_message = "Every spoke needs at least one subnet."
  }
}

variable "ram_allow_external_principals" {
  description = "Set true only if the application accounts are NOT in the same AWS Organization as this hub account. With false (the default) the Transit Gateway share is auto-accepted by accounts in the organisation, provided RAM sharing with the organisation has been enabled once in the management account: aws ram enable-sharing-with-aws-organization"
  type        = bool
  default     = false
}
