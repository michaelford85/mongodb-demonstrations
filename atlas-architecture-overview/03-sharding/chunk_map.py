"""Live chunk-distribution monitor for the sharding demo.

Every 2 seconds, prints the per-shard document count and storage size for the
demo collection. Run this in a side terminal while you execute each mongosh
strategy script — the output shows the balancer redistributing chunks in real
time after `sh.shardCollection()`.

Uses `collStats` (allowed on Atlas) rather than reading config.chunks directly.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure


COLLECTION = "events"
REFRESH_SECONDS = 2.0


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:6.1f} {unit}"
        n /= 1024
    return f"{n:6.1f} TB"


def fetch_shard_stats(db, ns: str) -> dict:
    """Return a dict of {shard_name: {count, size, storageSize}}."""
    try:
        stats = db.command("collStats", ns)
    except OperationFailure as exc:
        if "ns not found" in str(exc) or "does not exist" in str(exc):
            return {}
        raise
    shards = stats.get("shards") or {}
    if not shards:
        # Unsharded collection — single primary shard
        return {"(unsharded)": {"count": stats.get("count", 0), "size": stats.get("size", 0)}}
    return {
        name: {"count": s.get("count", 0), "size": s.get("size", 0)}
        for name, s in shards.items()
    }


def render(stats: dict) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"\n[{ts}]  chunk distribution for {COLLECTION}")
    if not stats:
        print("  (collection not found — run seed.py first)")
        return

    total = sum(s["count"] for s in stats.values()) or 1
    print(f"  {'SHARD':<32} {'DOCS':>10} {'PCT':>6}  {'SIZE':>10}")
    print("  " + "-" * 70)
    for shard, s in sorted(stats.items()):
        pct = 100.0 * s["count"] / total
        bar = "#" * int(pct / 2)
        print(
            f"  {shard:<32} {s['count']:>10,} {pct:>5.1f}%  "
            f"{human_bytes(s['size']):>10}  {bar}"
        )


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    uri = require_env("SHARDED_URI")
    db_name = os.getenv("DEMO_DB", "architecture_demo")

    client = MongoClient(uri)
    db = client[db_name]

    print(f"Watching {db_name}.{COLLECTION} on the sharded cluster.")
    print(f"Refresh every {REFRESH_SECONDS:.0f} s. Stop with Ctrl+C.")

    def handle_sigint(_sig, _frame):
        print("\nChunk monitor stopped.")
        client.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    while True:
        render(fetch_shard_stats(db, COLLECTION))
        time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    main()
