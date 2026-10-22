"""Latency percentiles and result serialization for benchmark runs."""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def percentile(sorted_values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile on an already-sorted list of latencies (ms)."""
    if not sorted_values:
        return None
    if pct <= 0:
        return sorted_values[0]
    if pct >= 100:
        return sorted_values[-1]
    rank = math.ceil((pct / 100) * len(sorted_values))
    return sorted_values[max(0, rank - 1)]


def latency_summary(samples_ms: list[float]) -> dict:
    ordered = sorted(samples_ms)
    return {
        "count": len(ordered),
        "p50_ms": percentile(ordered, 50),
        "p90_ms": percentile(ordered, 90),
        "p95_ms": percentile(ordered, 95),
        "p99_ms": percentile(ordered, 99),
        "max_ms": ordered[-1] if ordered else None,
    }


def save_results(results: dict, out_dir: str, stem: str) -> tuple[str, str]:
    """Write machine-readable JSON and a concise Markdown summary."""
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, f"{stem}.json")
    md_path = os.path.join(out_dir, f"{stem}.md")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, default=str)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(to_markdown(results))
    return json_path, md_path


def to_markdown(results: dict) -> str:
    lines = [f"# Benchmark result: {results.get('run_id', 'unnamed')}",
             "", f"- UTC start: {results.get('utc_start')}",
             f"- UTC end: {results.get('utc_end')}",
             f"- Cluster label: {results.get('cluster_label')}",
             f"- Namespace: {results.get('namespace')}",
             f"- Search index: {results.get('search_index_name')}",
             ""]
    for phase, data in results.get("phases", {}).items():
        lines.append(f"## {phase}")
        lines.append(f"```json\n{json.dumps(data, indent=2, default=str)}\n```")
    for warning in results.get("warnings", []):
        lines.append(f"> ⚠ {warning}")
    for note in results.get("operator_recorded", []):
        lines.append(f"- Operator-recorded: {note}")
    return "\n".join(lines) + "\n"
