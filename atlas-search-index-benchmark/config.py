"""Configuration and safety-cap validation for the Atlas Search benchmark.

All live behavior is opt-in and hard-capped. Defaults are plan-only.
Planning inputs (1.2-1.5 KB/doc, 100 QPS peak, 2000/2000/500 write ops/sec)
are UNVERIFIED estimates and are encoded only as labeled profiles/caps.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields

from dotenv import load_dotenv

# Hard safety ceilings. Raise deliberately via env with MAX_* variables,
# documented in README (they exist to make accidents hard, not to be smart).
HARD_LIMITS = {
    "max_doc_count": 2_000_000,
    "max_qps": 100.0,
    "max_concurrency": 64,
    "max_runtime_seconds": 7_200,
    "max_insert_per_sec": 500.0,
    "max_update_per_sec": 250.0,
    "max_delete_per_sec": 250.0,
    "max_batch_size": 5_000,
}


def _bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"true", "1", "yes"}


def _num(env: dict, key: str, default: float) -> float:
    raw = env.get(key, "")
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{key}={raw!r} is not a number")
    return value


@dataclass
class BenchmarkConfig:
    # Connection (never logged beyond sanitized host label)
    uri: str = ""
    cluster_label: str = "not-provided"

    # Dedicated demo namespace — never a production or business namespace.
    db_name: str = "search_bench_demo"
    collection_name: str = "bench_docs"
    search_index_name: str = "bench_lexical_index"
    index_definition_file: str = ""  # operator-supplied; default mapping otherwise

    # Gates
    allow_writes: bool = False      # ALLOW_ATLAS_BENCHMARK_WRITES=true
    confirmed: bool = False         # BENCHMARK_CONFIRM=yes
    assume_yes: bool = False        # CI-style non-interactive confirm after preview

    # Seed phase
    doc_count: int = 50_000
    batch_size: int = 1_000
    generator_seed: int = 42

    # Search load phase
    qps: float = 5.0                # synthetic baseline, unconfirmed planning input
    warmup_seconds: float = 10.0
    duration_seconds: float = 60.0
    concurrency: int = 4
    query_timeout_seconds: float = 10.0

    # Optional mixed workload (all default to 0 = off; opt-in, capped)
    insert_per_sec: float = 0.0
    update_per_sec: float = 0.0
    delete_per_sec: float = 0.0
    ttl_simulation: str = "none"    # none | delete_only (never creates TTL index)

    # Index-build polling
    poll_interval_seconds: float = 5.0
    index_ready_timeout_seconds: float = 3_600.0

    # Manual metadata (recorded in results; not inferred from the URI)
    search_node_tier: str = "not-configured"
    search_node_topology: str = "not-configured"

    problems: list = field(default_factory=list)

    @property
    def namespace(self) -> str:
        return f"{self.db_name}.{self.collection_name}"

    @property
    def live_allowed(self) -> bool:
        return bool(self.allow_writes and self.confirmed and self.uri)

    @property
    def mixed_enabled(self) -> bool:
        return (self.insert_per_sec + self.update_per_sec + self.delete_per_sec) > 0


def validate(cfg: BenchmarkConfig) -> list[str]:
    """Return a list of problems; empty means configuration is safe to use."""
    problems: list[str] = []
    for name, cap in HARD_LIMITS.items():
        value = getattr(cfg, name.replace("max_doc_count", "doc_count")
                        .replace("max_qps", "qps")
                        .replace("max_concurrency", "concurrency")
                        .replace("max_runtime_seconds", "duration_seconds")
                        .replace("max_insert_per_sec", "insert_per_sec")
                        .replace("max_update_per_sec", "update_per_sec")
                        .replace("max_delete_per_sec", "delete_per_sec")
                        .replace("max_batch_size", "batch_size"))
        if value > cap:
            problems.append(
                f"{name} exceeded: configured {value} > hard cap {cap} "
                f"(see README to raise deliberately)"
            )
    if cfg.duration_seconds > HARD_LIMITS["max_runtime_seconds"]:
        problems.append("duration_seconds over hard cap")
    for name in ("qps", "warmup_seconds", "duration_seconds", "insert_per_sec",
                 "update_per_sec", "delete_per_sec", "generator_seed",
                 "query_timeout_seconds", "index_ready_timeout_seconds"):
        if getattr(cfg, name) < 0:
            problems.append(f"{name} must be >= 0")
    if cfg.doc_count <= 0:
        problems.append("doc_count must be > 0")
    if cfg.concurrency <= 0:
        problems.append("concurrency must be > 0")
    if cfg.batch_size <= 0:
        problems.append("batch_size must be > 0")
    if cfg.poll_interval_seconds <= 0:
        problems.append("poll_interval_seconds must be > 0")
    if cfg.index_definition_file and not os.path.isfile(cfg.index_definition_file):
        problems.append(f"index_definition_file not found: {cfg.index_definition_file}")
    if cfg.ttl_simulation not in {"none", "delete_only"}:
        problems.append("ttl_simulation must be 'none' or 'delete_only'")
    for gate_name, value in (("ALLOW_ATLAS_BENCHMARK_WRITES", cfg.allow_writes),
                             ("BENCHMARK_CONFIRM", cfg.confirmed)):
        if value and not cfg.uri:
            problems.append(f"{gate_name} set but ATLAS_BENCHMARK_URI is empty")
    if cfg.mixed_enabled and not cfg.allow_writes:
        problems.append("write churn configured but ALLOW_ATLAS_BENCHMARK_WRITES is not true")
    return problems


def load_config(env: dict | None = None) -> BenchmarkConfig:
    if env is None:
        # Demo folder's .env is the single source of truth (repo convention).
        # Set BENCHMARK_NO_DOTENV=1 (or pass an env dict) to ignore it.
        if not _bool(os.environ.get("BENCHMARK_NO_DOTENV")):
            load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
        env = os.environ
    cfg = BenchmarkConfig(
        uri=(env.get("ATLAS_BENCHMARK_URI") or "").strip(),
        cluster_label=(env.get("CLUSTER_LABEL") or "not-provided").strip(),
        db_name=(env.get("ATLAS_BENCHMARK_DB") or "search_bench_demo").strip(),
        collection_name=(env.get("ATLAS_BENCHMARK_COLLECTION") or "bench_docs").strip(),
        search_index_name=(env.get("ATLAS_BENCHMARK_INDEX_NAME") or "bench_lexical_index").strip(),
        index_definition_file=(env.get("ATLAS_BENCHMARK_INDEX_DEFINITION") or "").strip(),
        allow_writes=_bool(env.get("ALLOW_ATLAS_BENCHMARK_WRITES")),
        confirmed=_bool(env.get("BENCHMARK_CONFIRM")),
        assume_yes=_bool(env.get("BENCHMARK_ASSUME_YES")),
        doc_count=int(_num(env, "DOC_COUNT", 50_000)),
        batch_size=int(_num(env, "BATCH_SIZE", 1_000)),
        generator_seed=int(_num(env, "GENERATOR_SEED", 42)),
        qps=_num(env, "LOAD_QPS", 5.0),
        warmup_seconds=_num(env, "LOAD_WARMUP_SECONDS", 10.0),
        duration_seconds=_num(env, "LOAD_DURATION_SECONDS", 60.0),
        concurrency=int(_num(env, "LOAD_CONCURRENCY", 4)),
        query_timeout_seconds=_num(env, "LOAD_QUERY_TIMEOUT_SECONDS", 10.0),
        insert_per_sec=_num(env, "MIXED_INSERT_PER_SEC", 0.0),
        update_per_sec=_num(env, "MIXED_UPDATE_PER_SEC", 0.0),
        delete_per_sec=_num(env, "MIXED_DELETE_PER_SEC", 0.0),
        ttl_simulation=(env.get("MIXED_TTL_SIMULATION") or "none").strip().lower(),
        poll_interval_seconds=_num(env, "INDEX_POLL_INTERVAL_SECONDS", 5.0),
        index_ready_timeout_seconds=_num(env, "INDEX_READY_TIMEOUT_SECONDS", 3600.0),
        search_node_tier=(env.get("SEARCH_NODE_TIER") or "not-configured").strip(),
        search_node_topology=(env.get("SEARCH_NODE_TOPOLOGY") or "not-configured").strip(),
    )
    cfg.problems = validate(cfg)
    return cfg


def summarize(cfg: BenchmarkConfig) -> dict:
    """Plan view safe to print/serialize: no credentials, no URI."""
    return {
        "namespace": cfg.namespace,
        "cluster_label": cfg.cluster_label,
        "search_index_name": cfg.search_index_name,
        "index_definition_source": cfg.index_definition_file or "default (illustrative lexical mapping — not equivalent to production mapping)",
        "live_allowed": cfg.live_allowed,
        "seed": {
            "doc_count": cfg.doc_count,
            "batch_size": cfg.batch_size,
            "generator_seed": cfg.generator_seed,
        },
        "search_load": {
            "qps": cfg.qps,
            "warmup_seconds": cfg.warmup_seconds,
            "duration_seconds": cfg.duration_seconds,
            "concurrency": cfg.concurrency,
            "profile_label": (
                "stress (unverified planning peak)" if cfg.qps > 10
                else "baseline (synthetic, unconfirmed planning input)"
            ),
        },
        "mixed_writes_opt_in": {
            "insert_per_sec": cfg.insert_per_sec,
            "update_per_sec": cfg.update_per_sec,
            "delete_per_sec": cfg.delete_per_sec,
            "note": "planning estimates (2000/2000/500 ops-sec) are NOT defaults and exceed hard caps",
        },
        "hard_limits": HARD_LIMITS,
        "manual_metadata": {
            "search_node_tier": cfg.search_node_tier,
            "search_node_topology": cfg.search_node_topology,
            "note": "entered by operator; not inferred from the URI",
        },
        "problems": cfg.problems,
    }
