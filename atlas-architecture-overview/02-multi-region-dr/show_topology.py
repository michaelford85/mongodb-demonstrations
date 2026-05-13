"""Snapshot of the replica set's current topology.

Prints one row per member showing host, state, priority, replication lag, and
(when Atlas exposes them as member tags) the cloud provider and region.

Run this before and after Atlas's "Test Primary Failover" to show that the
same data redistributes elastically across regions.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


STATE_NAMES = {
    0: "STARTUP",
    1: "PRIMARY",
    2: "SECONDARY",
    3: "RECOVERING",
    5: "STARTUP2",
    6: "UNKNOWN",
    7: "ARBITER",
    8: "DOWN",
    9: "ROLLBACK",
    10: "REMOVED",
}


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def member_tags(config_member: dict) -> str:
    """Return a 'provider/region' string from rs config member tags, if any."""
    tags = config_member.get("tags") or {}
    provider = tags.get("provider") or tags.get("cloudProvider") or "?"
    region = tags.get("region") or tags.get("regionName") or "?"
    return f"{provider}/{region}"


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    uri = require_env("REPLICASET_URI")
    client = MongoClient(uri)

    status = client.admin.command("replSetGetStatus")
    config = client.admin.command("replSetGetConfig")["config"]

    cfg_by_host = {m["host"]: m for m in config["members"]}

    primary_optime = next(
        (m["optimeDate"] for m in status["members"] if m["state"] == 1), None
    )

    print(f"\nReplica set : {status['set']}")
    print(f"Snapshot at : {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print(f"Members     : {len(status['members'])}\n")

    header = f"  {'HOST':<55} {'STATE':<10} {'PRIO':>4} {'LAG (s)':>8}  PROVIDER/REGION"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for m in status["members"]:
        host = m["host"]
        state = STATE_NAMES.get(m["state"], str(m["state"]))
        cfg = cfg_by_host.get(host, {})
        priority = cfg.get("priority", "?")
        if primary_optime and m.get("optimeDate"):
            lag = (primary_optime - m["optimeDate"]).total_seconds()
            lag_str = f"{lag:8.1f}"
        else:
            lag_str = f"{'-':>8}"
        print(
            f"  {host:<55} {state:<10} {priority:>4} {lag_str}  {member_tags(cfg)}"
        )

    print()
    client.close()


if __name__ == "__main__":
    main()
