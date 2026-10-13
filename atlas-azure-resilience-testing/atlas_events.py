"""Pull Atlas project events for a test window and build a node-transition timeline.

The Atlas control plane records elections, host state changes and cluster
maintenance as project events. Exporting them for the exact test window gives an
independent timeline to line up against writer.py and watcher.py output, and it
is the evidence that shows whether a node was restarted in place or replaced.

    python3 atlas_events.py --since-minutes 30 --label t3-failover-idle

Read-only. Requires an API key with at least Project Read Only.
"""

from __future__ import annotations

import argparse
from datetime import timedelta

from common import (artefact_path, atlas_paginate, load_env, require_env,
                    utc_now, write_json)

# Event types that matter for failover and node-replacement analysis. Anything
# else in the window is still exported, just not highlighted.
NOTABLE = {
    "PRIMARY_ELECTED",
    "REPLICA_SET_MEMBER_ADDED",
    "REPLICA_SET_MEMBER_REMOVED",
    "HOST_DOWN",
    "HOST_UP",
    "HOST_RECOVERED",
    "HOST_RESTARTED",
    "HOST_NOW_PRIMARY",
    "HOST_NOW_SECONDARY",
    "NO_PRIMARY",
    "TOO_MANY_ELECTIONS",
    "CLUSTER_INSTANCE_RESTARTED",
    "CLUSTER_MONGOS_RESTARTED",
    "MAINTENANCE_IN_ADVANCED",
    "MAINTENANCE_STARTED",
    "MAINTENANCE_NO_LONGER_NEEDED",
    "AUTOMATION_CONFIG_PUBLISHED_AUDIT",
    "CLUSTER_UPDATE_STARTED",
    "CLUSTER_UPDATE_COMPLETED",
    "DISK_AUTO_SCALED",
}


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Export Atlas events for a window")
    parser.add_argument("--label", required=True, help="Test case label")
    parser.add_argument("--since-minutes", type=int, default=30,
                        help="Window length ending now (default: 30)")
    args = parser.parse_args()

    project_id = require_env("ATLAS_PROJECT_ID")
    cluster_name = require_env("ATLAS_CLUSTER_NAME")

    max_date = utc_now()
    min_date = max_date - timedelta(minutes=args.since_minutes)

    events = list(atlas_paginate(
        f"/groups/{project_id}/events",
        {
            "minDate": min_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "maxDate": max_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    ))

    timeline = []
    for event in sorted(events, key=lambda e: e.get("created", "")):
        entry = {
            "created": event.get("created"),
            "eventTypeName": event.get("eventTypeName"),
            "clusterName": event.get("clusterName"),
            "hostname": event.get("hostname"),
            "port": event.get("port"),
            "replicaSetName": event.get("replicaSetName"),
            "notable": event.get("eventTypeName") in NOTABLE,
        }
        timeline.append(entry)

    payload = {
        "window": {"from": min_date, "to": max_date},
        "projectClusterFilter": cluster_name,
        "eventCount": len(timeline),
        "timeline": timeline,
    }

    print(f"\nWindow  : {min_date:%H:%M:%S} -> {max_date:%H:%M:%S} UTC")
    print(f"Events  : {len(timeline)} total\n")
    header = f"  {'CREATED':<22} {'EVENT':<34} HOST"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for entry in timeline:
        if not entry["notable"]:
            continue
        host = entry.get("hostname") or entry.get("clusterName") or "-"
        print(f"  {str(entry['created']):<22} {str(entry['eventTypeName']):<34} {host}")
    print()

    write_json(artefact_path(f"events-{args.label}", "json"), payload)


if __name__ == "__main__":
    main()
