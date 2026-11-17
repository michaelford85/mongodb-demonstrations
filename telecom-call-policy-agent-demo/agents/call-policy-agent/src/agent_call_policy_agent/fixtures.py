"""Fully synthetic seed data for the call-control policy demo.

Every record here is FICTIONAL and invented for a technical discussion.
No real customer records, credentials, or production endpoints
are used anywhere in this demo.
"""

DEMO_MARKER = {
    "demo": True,
    "note": "Fictional demo data - not real customer records",
}

ENTERPRISE = {
    "enterprise_id": "demo_enterprise_001",
    "legal_name": "Demo Enterprise One (FICTITIOUS)",
    "industry": "Business services",
    "status": "verified",
    "display_name": "Demo Enterprise One",
    "note": "Fictional enterprise created for this demo",
}

CARRIER_RELATIONSHIPS = [
    {
        "relationship_id": "rel-001",
        "carrier_id": "demo_carrier_001",
        "carrier_name": "Demo Carrier One (FICTITIOUS)",
        "enterprise_id": "demo_enterprise_001",
        "status": "active",
        "origin_countries": ["US", "CA"],
        "trunk_ids": ["trunk-c001-1", "trunk-c001-2"],
        "note": "Fictional carrier relationship created for this demo",
    },
    {
        "relationship_id": "rel-002",
        "carrier_id": "demo_carrier_002",
        "carrier_name": "Demo Carrier Two (FICTITIOUS)",
        "enterprise_id": "demo_enterprise_001",
        "status": "provisioning",
        "origin_countries": ["US"],
        "trunk_ids": ["trunk-c002-1"],
        "note": "Fictional carrier relationship created for this demo",
    },
]

BRAND_METADATA = [
    {
        "brand_id": "demo_brand_001",
        "enterprise_id": "demo_enterprise_001",
        "display_name": "Demo Enterprise One",
        "call_reason": "Account service",
        "logo_ref": "demo://logos/demo-brand-001.png",
        "status": "approved",
        "note": "Fictional brand metadata created for this demo",
    },
    {
        "brand_id": "demo_brand_002",
        "enterprise_id": "demo_enterprise_001",
        "display_name": "Demo Enterprise One - Servicing",
        "call_reason": "Payment reminder",
        "logo_ref": "demo://logos/demo-brand-002.png",
        "status": "approved",
        "note": "Fictional brand metadata created for this demo",
    },
]

SAMPLE_CALLS = [
    {
        "call_id": "call-001",
        "description": "Demo Carrier One trunk, verified US enterprise number",
        "from_number": "+15551230001",
        "carrier_id": "demo_carrier_001",
        "trunk_id": "trunk-c001-1",
        "origin_country": "US",
        "enterprise_id": "demo_enterprise_001",
    },
    {
        "call_id": "call-002",
        "description": "Demo Carrier One trunk, unregistered number",
        "from_number": "+15559990001",
        "carrier_id": "demo_carrier_001",
        "trunk_id": "trunk-c001-1",
        "origin_country": "US",
        "enterprise_id": None,
    },
    {
        "call_id": "call-003",
        "description": "Unknown international origin on Demo Carrier Two",
        "from_number": "+441234567890",
        "carrier_id": "demo_carrier_002",
        "trunk_id": "trunk-c002-1",
        "origin_country": "GB",
        "enterprise_id": None,
    },
    {
        "call_id": "call-004",
        "description": "Collections line of the fictional enterprise",
        "from_number": "+15551230002",
        "carrier_id": "demo_carrier_001",
        "trunk_id": "trunk-c001-2",
        "origin_country": "US",
        "enterprise_id": "demo_enterprise_001",
    },
]

# Version 1 of the fictional call-control policy. Published state; read by the
# deterministic evaluator.
POLICY_V1 = {
    "policy_id": "demo-call-policy",
    "policy_version": 1,
    "status": "active",
    "label": "Baseline fictional call-control policy (demo)",
    "created_at": "2026-01-05T14:00:00+00:00",
    "activated_at": "2026-01-05T15:00:00+00:00",
    "rules": [
        {
            "rule_id": "rule-001",
            "priority": 10,
            "match": {
                "enterprise_id": "demo_enterprise_001",
                "carrier_id": "demo_carrier_001",
                "origin_countries": ["US"],
            },
            "action": "deliver_with_brand",
            "brand_id": "demo_brand_001",
            "rationale": "Verified US enterprise traffic on an active trunk is delivered with the approved brand.",
        },
        {
            "rule_id": "rule-002",
            "priority": 5,
            "match": {
                "enterprise_id": "demo_enterprise_001",
                "number_prefix": "+15551230002",
                "carrier_id": "demo_carrier_001",
                "origin_countries": ["US"],
            },
            "action": "deliver_with_brand",
            "brand_id": "demo_brand_002",
            "rationale": "Collections lines use the servicing brand.",
        },
    ],
    "default_action": "block",
    "note": "Fictional policy created for this demo",
}

ALL_FIXTURES = {
    "enterprise": ENTERPRISE,
    "carrier_relationships": CARRIER_RELATIONSHIPS,
    "brand_metadata": BRAND_METADATA,
    "sample_calls": SAMPLE_CALLS,
    "policy_v1": POLICY_V1,
}
