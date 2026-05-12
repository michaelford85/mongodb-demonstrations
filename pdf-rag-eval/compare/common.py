"""Shared helpers for the Cosmos-vs-Atlas comparison demos.

Keeps the per-demo scripts focused on what they're demonstrating. Common
needs: a small canned query set, on-demand Voyage embedding (cached so
repeated runs don't re-embed), latency math, and a compact table printer.
"""
from __future__ import annotations

import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Settings  # noqa: E402
from embeddings import embed_query  # noqa: E402

# Five canned queries the demos rotate through. Kept short so the embed
# calls don't dominate the comparison signal we're trying to surface.
CANNED_QUERIES: tuple[str, ...] = (
    "What are the recommended safety procedures?",
    "Summarise the quarterly performance metrics.",
    "Describe the onboarding workflow for new engineers.",
    "What is the policy on expense reimbursement?",
    "How is data quality measured?",
)


@dataclass(frozen=True)
class Timing:
    """Per-request outcome record. error is None on success."""
    latency_ms: float
    error: str | None = None


def embed_canned_queries(settings: Settings) -> list[list[float]]:
    """Embed every canned query once with input_type='query'. Cached caller-side."""
    return [
        embed_query(q, settings.voyage_api_key, settings.voyage_model, settings.embed_dim)
        for q in CANNED_QUERIES
    ]


def time_call(fn: Callable[[], object]) -> Timing:
    """Run fn once, return latency + optional error string."""
    start = time.perf_counter()
    try:
        fn()
        return Timing((time.perf_counter() - start) * 1000.0)
    except Exception as exc:  # noqa: BLE001 — we want every backend exception here
        return Timing(
            (time.perf_counter() - start) * 1000.0,
            error=f"{type(exc).__name__}: {exc}"[:200],
        )


def percentile(values: Iterable[float], pct: float) -> float:
    """Nearest-rank percentile, returns 0.0 when the sequence is empty."""
    data = sorted(values)
    if not data:
        return 0.0
    k = max(0, min(len(data) - 1, int(round(pct / 100.0 * (len(data) - 1)))))
    return data[k]


@dataclass
class Stats:
    backend: str
    total: int
    successes: int
    errors: int
    throttled: int            # Cosmos: HTTP 429 / TooManyRequests
    elapsed_s: float
    successful_latencies_ms: list[float]

    @property
    def throughput_rps(self) -> float:
        return self.successes / self.elapsed_s if self.elapsed_s > 0 else 0.0

    @property
    def p50_ms(self) -> float:
        return percentile(self.successful_latencies_ms, 50)

    @property
    def p95_ms(self) -> float:
        return percentile(self.successful_latencies_ms, 95)

    @property
    def p99_ms(self) -> float:
        return percentile(self.successful_latencies_ms, 99)


def summarise(backend: str, timings: list[Timing], elapsed_s: float) -> Stats:
    successes = [t for t in timings if t.error is None]
    errors = [t for t in timings if t.error is not None]
    throttled = sum(1 for t in errors if _looks_throttled(t.error or ""))
    return Stats(
        backend=backend,
        total=len(timings),
        successes=len(successes),
        errors=len(errors),
        throttled=throttled,
        elapsed_s=elapsed_s,
        successful_latencies_ms=[t.latency_ms for t in successes],
    )


def _looks_throttled(message: str) -> bool:
    lowered = message.lower()
    return (
        "429" in message
        or "toomanyrequest" in lowered
        or "request rate is large" in lowered
        or "request rate is too large" in lowered
    )


def format_stats_table(rows: list[Stats]) -> str:
    """Render a fixed-width comparison table without external deps."""
    cols = (
        ("backend", lambda s: s.backend),
        ("total", lambda s: f"{s.total}"),
        ("ok", lambda s: f"{s.successes}"),
        ("errors", lambda s: f"{s.errors}"),
        ("throttled", lambda s: f"{s.throttled}"),
        ("rps", lambda s: f"{s.throughput_rps:.1f}"),
        ("p50 ms", lambda s: f"{s.p50_ms:.1f}"),
        ("p95 ms", lambda s: f"{s.p95_ms:.1f}"),
        ("p99 ms", lambda s: f"{s.p99_ms:.1f}"),
    )
    widths = [
        max(len(name), *(len(getter(row)) for row in rows))
        for name, getter in cols
    ]
    header = "  ".join(name.ljust(w) for (name, _), w in zip(cols, widths))
    sep = "  ".join("-" * w for w in widths)
    body = "\n".join(
        "  ".join(getter(row).ljust(w) for (_, getter), w in zip(cols, widths))
        for row in rows
    )
    return f"{header}\n{sep}\n{body}"
