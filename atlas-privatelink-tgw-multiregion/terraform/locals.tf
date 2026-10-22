locals {
  # ── Tags ─────────────────────────────────────────────────────────────────────
  # Applied through each provider's default_tags, so every resource in the root
  # module and in the child modules carries them without repetition. The
  # mandatory five are merged last so extra_tags can never unset them.
  mandatory_tags = merge(
    var.extra_tags,
    {
      Project     = var.tag_project
      Environment = var.tag_environment
      Owner       = var.tag_owner
      Purpose     = var.tag_purpose
      ManagedBy   = "Terraform"
    },
  )

  # ── Region keys ──────────────────────────────────────────────────────────────
  hub_keys          = sort(keys(var.hubs))
  client_region_key = var.client.region_key

  # Distinct ASN per Transit Gateway unless the operator pinned one. Peered
  # gateways on the same ASN work, but distinct ASNs keep route origins
  # readable in the TGW route tables.
  hub_asns = {
    for idx, key in local.hub_keys :
    key => coalesce(var.hubs[key].amazon_side_asn, 64512 + idx)
  }

  # ── CIDR inventory ───────────────────────────────────────────────────────────
  # Every VPC in the lab, keyed by a human-readable label used in error
  # messages. These are also the only prefixes this lab ever routes: there is
  # deliberately no 0.0.0.0/0 route pointing at a Transit Gateway.
  vpc_cidrs = merge(
    { "client-${local.client_region_key}" = var.client.vpc_cidr_block },
    { for key, hub in var.hubs : "hub-${key}" => hub.vpc_cidr_block },
    { for key, spoke in var.spokes : "spoke-${key} (acct ${spoke.account_id})" => spoke.vpc_cidr_block },
  )

  vpc_labels = sort(keys(local.vpc_cidrs))

  # Every unordered pair of VPCs, compared once. Terraform cannot order strings
  # with <, so the "compare once" filter runs on the positions instead.
  vpc_cidr_pairs = [
    for pair in setproduct(range(length(local.vpc_labels)), range(length(local.vpc_labels))) : {
      a_label = local.vpc_labels[pair[0]]
      b_label = local.vpc_labels[pair[1]]
      a_cidr  = local.vpc_cidrs[local.vpc_labels[pair[0]]]
      b_cidr  = local.vpc_cidrs[local.vpc_labels[pair[1]]]
    }
    if pair[0] < pair[1]
  ]

  # Two IPv4 blocks overlap if, and only if, one block's network address falls
  # inside the other. Masking B's network address down to A's prefix length and
  # comparing it to A's network address is the containment test; run it both
  # ways round to catch either nesting direction.
  overlapping_vpc_cidrs = [
    for pair in local.vpc_cidr_pairs :
    "${pair.a_label} (${pair.a_cidr}) overlaps ${pair.b_label} (${pair.b_cidr})"
    if cidrhost(pair.a_cidr, 0) == cidrhost("${cidrhost(pair.b_cidr, 0)}/${split("/", pair.a_cidr)[1]}", 0) ||
    cidrhost(pair.b_cidr, 0) == cidrhost("${cidrhost(pair.a_cidr, 0)}/${split("/", pair.b_cidr)[1]}", 0)
  ]

  # Subnets, grouped by the VPC they belong to.
  subnet_sets = merge(
    {
      "client-${local.client_region_key}" = {
        vpc_cidr = var.client.vpc_cidr_block
        subnets = concat(
          var.client.subnet_cidrs,
          var.client.nat_subnet_cidr != "" ? [var.client.nat_subnet_cidr] : [],
        )
      }
    },
    {
      for key, hub in var.hubs : "hub-${key}" => {
        vpc_cidr = hub.vpc_cidr_block
        subnets  = hub.subnet_cidrs
      }
    },
    {
      for key, spoke in var.spokes : "spoke-${key}" => {
        vpc_cidr = spoke.vpc_cidr_block
        subnets = concat(
          spoke.subnet_cidrs,
          spoke.nat_subnet_cidr != "" ? [spoke.nat_subnet_cidr] : [],
        )
      }
    },
  )

  subnets_outside_their_vpc = flatten([
    for label, set in local.subnet_sets : [
      for subnet in set.subnets :
      "${label}: ${subnet} is not inside ${set.vpc_cidr}"
      if tonumber(split("/", subnet)[1]) < tonumber(split("/", set.vpc_cidr)[1]) ||
      cidrhost(set.vpc_cidr, 0) != cidrhost("${cidrhost(subnet, 0)}/${split("/", set.vpc_cidr)[1]}", 0)
    ]
  ])

  overlapping_subnets = flatten([
    for label, set in local.subnet_sets : [
      for pair in setproduct(range(length(set.subnets)), range(length(set.subnets))) :
      "${label}: ${set.subnets[pair[0]]} overlaps ${set.subnets[pair[1]]}"
      if pair[0] < pair[1] && (
        cidrhost(set.subnets[pair[0]], 0) == cidrhost("${cidrhost(set.subnets[pair[1]], 0)}/${split("/", set.subnets[pair[0]])[1]}", 0) ||
        cidrhost(set.subnets[pair[1]], 0) == cidrhost("${cidrhost(set.subnets[pair[0]], 0)}/${split("/", set.subnets[pair[1]])[1]}", 0)
      )
    ]
  ])

  # AWS accepts /16 to /28 for a VPC. Catching it here gives a readable error
  # before any API call, and rules out 0.0.0.0/0 as a "CIDR" by construction.
  badly_sized_vpc_cidrs = [
    for label, cidr in local.vpc_cidrs :
    "${label} (${cidr}) must be between /16 and /28"
    if tonumber(split("/", cidr)[1]) < 16 || tonumber(split("/", cidr)[1]) > 28
  ]

  single_az_hubs = [
    for key in local.hub_keys :
    "hub-${key} (${var.hubs[key].aws_region}) has only ${length(var.hubs[key].subnet_cidrs)} endpoint subnet"
    if length(var.hubs[key].subnet_cidrs) < 2
  ]

  # ── Routing inputs ───────────────────────────────────────────────────────────
  # Every prefix on the consuming side of the lab: the hub account's own client
  # VPC plus each application account's spoke VPC. These are what the hub
  # endpoint security groups admit, what the hub VPCs route back to, and what
  # region B needs static routes for over the peering. Security groups cannot
  # reference groups across accounts or regions, so this list is the boundary.
  spoke_keys         = sort(keys(var.spokes))
  spoke_cidr_blocks  = [for key in local.spoke_keys : var.spokes[key].vpc_cidr_block]
  client_cidr_blocks = concat([var.client.vpc_cidr_block], local.spoke_cidr_blocks)
  hub_cidr_blocks    = [for key in local.hub_keys : var.hubs[key].vpc_cidr_block]

  # Prefixes reachable across the inter-region peering, per region key. Region A
  # holds the client VPC, so it must reach every remote hub; every remote region
  # must reach the client VPC. Peering carries no transit, so this stays a set
  # of point-to-point statements rather than a summarised supernet.
  remote_hub_cidrs_from_client_region = [
    for key in local.hub_keys :
    var.hubs[key].vpc_cidr_block
    if key != local.client_region_key
  ]
}

locals {
  # ── Test targets ─────────────────────────────────────────────────────────────
  # Every interface endpoint in the lab, flattened for the on-instance test
  # script. AWS-generated endpoint hostnames only: no Atlas connection string
  # and no credentials pass through here, user data or state.
  hub_modules = {
    a = module.hub_a
    b = module.hub_b
    # c = module.hub_c
  }

  endpoint_targets = flatten([
    for key, hub in local.hub_modules : [
      for label, dns_name in hub.endpoint_regional_dns_names : {
        region_key   = key
        aws_region   = var.hubs[key].aws_region
        label        = label
        dns_name     = dns_name
        hub_cidr     = var.hubs[key].vpc_cidr_block
        cross_region = key != local.client_region_key
      }
    ]
  ])
}
