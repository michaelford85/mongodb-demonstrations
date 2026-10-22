"""Deterministic synthetic document generation for the benchmark.

~20 fields: text strings (~30-char average, a labeled planning assumption),
filter/token-like low-cardinality fields, numbers, timestamps, and three
array fields. Deterministic given (seed, sequence number). No customer data.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import uuid

STATUSES = ["active", "pending", "archived", "draft", "review"]
CATEGORIES = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]
REGIONS = ["eu-west", "eu-central", "us-east", "us-south"]
WORD_POOL = [
    "mongodb", "atlas", "search", "index", "latency", "throughput", "cluster",
    "region", "replica", "lucene", "analyzer", "token", "filter", "query",
    "benchmark", "node", "tier", "storage", "freshness", "pipeline",
    "engineering", "platform", "service", "network", "storage", "gateway",
    "catalog", "invoice", "ledger", "sensor", "telemetry", "signal",
]

FIELD_COUNT = 20


def _stable_rng(seed: int, seq: int):
    import random
    return random.Random(f"{seed}:{seq}".encode().hex())


def _words(rng, count: int, avg_len: int = 30) -> str:
    # Approximate the configured average string length by sizing word count.
    words = [WORD_POOL[rng.randrange(len(WORD_POOL))] for _ in range(max(1, count))]
    text = " ".join(words)
    # Pad/trim toward the requested average length deterministically.
    target = max(avg_len, 4)
    while len(text) < target:
        text = (text + " " + WORD_POOL[rng.randrange(len(WORD_POOL))])[: len(text) + 12]
    return text[:target] if len(text) > target * 2 else text


def make_document(seq: int, seed: int = 42, avg_string_len: int = 30,
                  array_max_sizes: dict | None = None) -> dict:
    """Return one deterministic synthetic document. Same inputs -> same doc."""
    rng = _stable_rng(seed, seq)
    sizes = {"tags": 4, "authors": 3, "line_items": 5}
    if array_max_sizes:
        sizes.update(array_max_sizes)

    created = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(
        seconds=seq % (86400 * 365))
    tag_count = rng.randint(0, sizes["tags"])
    author_count = rng.randint(1, sizes["authors"])
    items_count = rng.randint(1, sizes["line_items"])

    return {
        "_id": f"bench-{seq:08d}",
        "title": _words(rng, 4, avg_string_len),
        "summary": _words(rng, 6, avg_string_len),
        "body": _words(rng, 12, avg_string_len),
        "category": CATEGORIES[rng.randrange(len(CATEGORIES))],
        "status": STATUSES[rng.randrange(len(STATUSES))],
        "region": REGIONS[rng.randrange(len(REGIONS))],
        "priority": rng.randint(1, 5),
        "score": round(rng.random() * 100, 2),
        "views": rng.randint(0, 50_000),
        "is_public": rng.random() < 0.8,
        "created_at": created,
        "updated_at": created + dt.timedelta(minutes=rng.randint(0, 1440)),
        "owner_id": f"owner-{rng.randint(1, 10_000)}",
        "language": "en" if rng.random() < 0.9 else "de",
        "version": rng.randint(1, 20),
        "tags": [WORD_POOL[rng.randrange(len(WORD_POOL))] for _ in range(tag_count)],
        "authors": [f"author-{rng.randint(1, 500)}" for _ in range(author_count)],
        "line_items": [
            {"sku": f"sku-{rng.randint(1, 5000)}", "qty": rng.randint(1, 10),
             "price": round(rng.random() * 500, 2)}
            for _ in range(items_count)
        ],
    }


def iter_documents(count: int, seed: int = 42, avg_string_len: int = 30,
                   start: int = 0, array_max_sizes: dict | None = None):
    """Yield deterministic documents from `start` (enables resumable seeding)."""
    for seq in range(start, start + count):
        yield make_document(seq, seed, avg_string_len, array_max_sizes)


def document_fingerprint(doc: dict) -> str:
    """Stable fingerprint for test assertions (sha256 of canonical JSON)."""
    payload = {k: str(v) for k, v in sorted(doc.items()) if k != "_id"}
    return hashlib.sha256(json_canonical(payload).encode()).hexdigest()[:16]


def json_canonical(obj) -> str:
    import json
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def query_terms(seed: int, count: int = 20) -> list[str]:
    """Deterministic representative search terms drawn from the word pool."""
    rng = _stable_rng(seed, 999_999)
    return [WORD_POOL[rng.randrange(len(WORD_POOL))] for _ in range(count)]
