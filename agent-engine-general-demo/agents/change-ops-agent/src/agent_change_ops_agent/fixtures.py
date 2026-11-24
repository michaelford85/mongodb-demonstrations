"""Fully synthetic seed data for the operational change demo.

Every record here is FICTIONAL and invented for a technical demonstration.
No real company, customer, policy, or personal data is used anywhere in
this demo. All identifiers use generic demo_* names on purpose.
"""

DEMO_MARKER = {
    "demo": True,
    "note": "Fictional demo data - not real organizations or records",
}

WORKSPACE = {
    "workspace_id": "demo_workspace_001",
    "display_name": "Demo Workspace One (FICTITIOUS)",
    "status": "verified",
    "description": "Synthetic workspace used to exercise the change lifecycle demo",
    "note": "Fictional workspace created for this demo",
}

SERVICES = [
    {
        "service_id": "demo_service_001",
        "workspace_id": "demo_workspace_001",
        "service_name": "Demo Service One (FICTITIOUS)",
        "status": "active",
        "regions": ["us-demo-1", "eu-demo-1"],
        "note": "Fictional service created for this demo",
    },
    {
        "service_id": "demo_service_002",
        "workspace_id": "demo_workspace_001",
        "service_name": "Demo Service Two (FICTITIOUS)",
        "status": "provisioning",
        "regions": ["us-demo-1"],
        "note": "Fictional service created for this demo",
    },
]

TAG_METADATA = [
    {
        "tag_id": "demo_tag_001",
        "workspace_id": "demo_workspace_001",
        "display_name": "Standard handling",
        "description": "Synthetic routing tag for standard handling of allowed requests",
        "status": "approved",
        "note": "Fictional tag metadata created for this demo",
    },
    {
        "tag_id": "demo_tag_002",
        "workspace_id": "demo_workspace_001",
        "display_name": "Priority handling",
        "description": "Synthetic routing tag reserved for elevated-priority requests",
        "status": "approved",
        "note": "Fictional tag metadata created for this demo",
    },
]

SAMPLE_CASES = [
    {
        "case_id": "case-001",
        "description": "Known service, standard request type, verified workspace",
        "service_id": "demo_service_001",
        "request_type": "standard",
        "region": "us-demo-1",
        "environment": "prod",
        "workspace_id": "demo_workspace_001",
    },
    {
        "case_id": "case-002",
        "description": "Unknown request type on an active service",
        "service_id": "demo_service_001",
        "request_type": "experimental",
        "region": "us-demo-1",
        "environment": "prod",
        "workspace_id": "demo_workspace_001",
    },
    {
        "case_id": "case-003",
        "description": "Provisioning service in the alternate region",
        "service_id": "demo_service_002",
        "request_type": "standard",
        "region": "eu-demo-1",
        "environment": "prod",
        "workspace_id": "demo_workspace_001",
    },
    {
        "case_id": "case-004",
        "description": "Elevated-priority request on an active service",
        "service_id": "demo_service_001",
        "request_type": "priority",
        "region": "us-demo-1",
        "environment": "prod",
        "workspace_id": "demo_workspace_001",
    },
]

# Synthetic change notes: past change requests and runbook-style notes used by
# the OPTIONAL semantic retrieval tool (Atlas Automated Embedding + Vector
# Search) and by the keyword fallback in mock mode.
CHANGE_NOTES = [
    {
        "note_id": "note-001",
        "workspace_id": "demo_workspace_001",
        "title": "Provisioning service traffic in eu-demo-1",
        "note_text": (
            "Previous change request asked whether demo_service_002 traffic "
            "originating in eu-demo-1 should be allowed while the service is "
            "still provisioning. The earlier decision was to deny it until the "
            "service finished provisioning."
        ),
        "related_service_id": "demo_service_002",
        "note": "Fictional change note created for this demo",
    },
    {
        "note_id": "note-002",
        "workspace_id": "demo_workspace_001",
        "title": "Priority request handling expectations",
        "note_text": (
            "Requests marked as priority type on demo_service_001 should be "
            "allowed with the priority handling tag so downstream tooling can "
            "distinguish them from standard requests."
        ),
        "related_service_id": "demo_service_001",
        "note": "Fictional change note created for this demo",
    },
    {
        "note_id": "note-003",
        "workspace_id": "demo_workspace_001",
        "title": "Experimental request types stay denied",
        "note_text": (
            "The workspace currently has no approved process for experimental "
            "request types, so any configuration allowing them was rejected in "
            "review. Keep the default deny until a process exists."
        ),
        "related_service_id": None,
        "note": "Fictional change note created for this demo",
    },
    {
        "note_id": "note-004",
        "workspace_id": "demo_workspace_001",
        "title": "Tag catalog reference",
        "note_text": (
            "Two approved tags exist for demo_workspace_001: standard handling "
            "and priority handling. Configuration directives must reference one "
            "of these tag identifiers when using allow_with_tag."
        ),
        "related_service_id": None,
        "note": "Fictional change note created for this demo",
    },
]

# Version 1 of the fictional operating configuration. Published state; read by
# the deterministic evaluator.
CONFIG_V1 = {
    "config_id": "demo-op-config",
    "config_version": 1,
    "status": "active",
    "label": "Baseline fictional operating configuration (demo)",
    "created_at": "2026-01-05T14:00:00+00:00",
    "activated_at": "2026-01-05T15:00:00+00:00",
    "directives": [
        {
            "directive_id": "dir-001",
            "priority": 10,
            "match": {
                "service_id": "demo_service_001",
                "request_type": "standard",
            },
            "action": "allow_with_tag",
            "tag_id": "demo_tag_001",
            "rationale": "Standard requests on the active demo service get standard handling.",
        },
        {
            "directive_id": "dir-002",
            "priority": 5,
            "match": {
                "service_id": "demo_service_001",
                "request_type": "priority",
            },
            "action": "allow_with_tag",
            "tag_id": "demo_tag_002",
            "rationale": "Priority requests get the priority handling tag.",
        },
    ],
    "default_action": "deny",
    "note": "Fictional configuration created for this demo",
}

ALL_FIXTURES = {
    "workspace": WORKSPACE,
    "services": SERVICES,
    "tag_metadata": TAG_METADATA,
    "sample_cases": SAMPLE_CASES,
    "change_notes": CHANGE_NOTES,
    "config_v1": CONFIG_V1,
}
