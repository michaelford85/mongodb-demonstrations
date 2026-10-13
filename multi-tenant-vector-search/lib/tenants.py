"""Synthetic multi-tenant corpus and the small/large tenant split.

Two profiles model the two regimes the architecture is built for:

  demo   — a handful of small tenants plus a couple of large ones, sized so a
           full run with real Voyage embeddings is quick and cheap.
  scale  — hundreds of small tenants plus large tenants that cross the
           ~10k-vectors-per-tenant line where a dedicated HNSW index earns its
           keep. Pair with --fake-embeddings to skip a large embedding bill.

Which tenants are "large" is data, not a heuristic: the large tenants get their
own View + HNSW index, everyone else shares the flat index. create_indexes and
the router both read this split so they never disagree.
"""
import random

PROFILES = {
    "demo": {
        "small_tenants": 12,
        "small_docs": 120,
        "large": {"globex": 2000, "initech": 2500},
    },
    "scale": {
        "small_tenants": 800,
        "small_docs": 120,
        "large": {"globex": 40000, "initech": 55000, "umbrella": 50000},
    },
}

# Building blocks for short, semantically varied documents. Combining a topic
# with a subject and a detail gives each tenant a corpus where semantic search
# meaningfully beats keyword matching.
_TOPICS = [
    "onboarding a new customer", "resetting a forgotten password",
    "configuring single sign-on", "exporting monthly invoices",
    "rotating an expired API key", "diagnosing slow dashboard load times",
    "enabling multi-factor authentication", "migrating data between regions",
    "setting up a webhook integration", "recovering a deleted project",
    "upgrading to the enterprise plan", "throttling a noisy background job",
]
_DETAILS = [
    "The support agent walked the admin through each step and confirmed success.",
    "A known edge case affects accounts created before the platform migration.",
    "Escalated to engineering after the standard runbook did not resolve it.",
    "Resolved by clearing the cached session token and retrying the request.",
    "Root cause was a misconfigured pre-filter on the tenant's saved query.",
    "Documented in the internal knowledge base for future reference.",
]


def small_tenant_ids(profile: str) -> list:
    n = PROFILES[profile]["small_tenants"]
    return [f"small_{i:04d}" for i in range(n)]


def large_tenant_ids(profile: str) -> list:
    return list(PROFILES[profile]["large"].keys())


def all_tenant_ids(profile: str) -> list:
    return small_tenant_ids(profile) + large_tenant_ids(profile)


def is_large(profile: str, tenant_id: str) -> bool:
    return tenant_id in PROFILES[profile]["large"]


def _docs_for(tenant_id: str, count: int, rng: random.Random):
    for i in range(count):
        topic = rng.choice(_TOPICS)
        detail = rng.choice(_DETAILS)
        text = (
            f"Ticket for tenant {tenant_id}: {topic}. {detail} "
            f"(reference {tenant_id}-{i:06d})"
        )
        yield {
            "tenant_id": tenant_id,
            "doc_id": f"{tenant_id}-{i:06d}",
            "category": topic,
            "text": text,
        }


def generate_documents(profile: str, seed: int = 42):
    """Yield every document for a profile, small tenants then large tenants."""
    cfg = PROFILES[profile]
    rng = random.Random(seed)
    for tid in small_tenant_ids(profile):
        yield from _docs_for(tid, cfg["small_docs"], rng)
    for tid, count in cfg["large"].items():
        yield from _docs_for(tid, count, rng)


def total_documents(profile: str) -> int:
    cfg = PROFILES[profile]
    return cfg["small_tenants"] * cfg["small_docs"] + sum(cfg["large"].values())
