"""Capture the pre-test baseline for the test cluster.

Records two independent views so later observations can be attributed to a
known starting state:

  * Control plane — the Atlas cluster description, including provider, region
    layout, instance size and the storage attributes that decide whether a
    replaced node can reuse its volume or must perform an initial sync.
  * Data plane — replica set membership, member states, priorities, replication
    lag, server version and storage engine.

Read-only. Run once before each test case and keep the artefact with the run.

    python3 baseline.py
"""

from __future__ import annotations

from pymongo import MongoClient

from common import (STATE_NAMES, artefact_path, atlas_get, load_env,
                    require_env, scoped_uri, utc_now, write_json)

# Storage-relevant keys pulled out of each regionConfig for quick comparison.
STORAGE_KEYS = (
    "providerName",
    "backingProviderName",
    "regionName",
    "priority",
    "electableSpecs",
    "readOnlySpecs",
    "analyticsSpecs",
)


def control_plane_facts() -> dict:
    project_id = require_env("ATLAS_PROJECT_ID")
    cluster_name = require_env("ATLAS_CLUSTER_NAME")
    cluster = atlas_get(f"/groups/{project_id}/clusters/{cluster_name}")

    specs = []
    for spec in cluster.get("replicationSpecs", []):
        specs.append(
            {
                "zoneName": spec.get("zoneName"),
                "regionConfigs": [
                    {key: config.get(key) for key in STORAGE_KEYS}
                    for config in spec.get("regionConfigs", [])
                ],
            }
        )

    return {
        "name": cluster.get("name"),
        "clusterType": cluster.get("clusterType"),
        "mongoDBVersion": cluster.get("mongoDBVersion"),
        "diskSizeGB": cluster.get("diskSizeGB"),
        "encryptionAtRestProvider": cluster.get("encryptionAtRestProvider"),
        "backupEnabled": cluster.get("backupEnabled"),
        "pitEnabled": cluster.get("pitEnabled"),
        "replicationSpecs": specs,
        "stateName": cluster.get("stateName"),
    }


def data_plane_facts(client: MongoClient) -> dict:
    status = client.admin.command("replSetGetStatus")
    config = client.admin.command("replSetGetConfig")["config"]
    build = client.admin.command("buildInfo")

    cfg_by_host = {m["host"]: m for m in config["members"]}
    primary_optime = next(
        (m["optimeDate"] for m in status["members"] if m["state"] == 1), None
    )

    members = []
    for member in status["members"]:
        cfg = cfg_by_host.get(member["host"], {})
        lag = None
        if primary_optime and member.get("optimeDate"):
            lag = (primary_optime - member["optimeDate"]).total_seconds()
        members.append(
            {
                "host": member["host"],
                "state": STATE_NAMES.get(member["state"], member["state"]),
                "priority": cfg.get("priority"),
                "votes": cfg.get("votes"),
                "tags": cfg.get("tags"),
                "lagSeconds": lag,
            }
        )

    facts = {
        "setName": status["set"],
        "serverVersion": build.get("version"),
        "electionTimeoutMillis": config.get("settings", {}).get(
            "electionTimeoutMillis"
        ),
        "heartbeatIntervalMillis": config.get("settings", {}).get(
            "heartbeatIntervalMillis"
        ),
        "members": members,
    }

    try:
        server_status = client.admin.command("serverStatus")
        facts["storageEngine"] = server_status.get("storageEngine", {}).get("name")
        facts["uptimeSeconds"] = server_status.get("uptime")
    except Exception as exc:  # noqa: BLE001 - permissions vary by cluster tier
        facts["storageEngine"] = f"unavailable ({type(exc).__name__})"

    return facts


def main() -> None:
    load_env()
    # Read-only throughout, so clusterMonitor is sufficient.
    uri = scoped_uri("MONITOR_CLUSTER_URI")

    client = MongoClient(uri)
    try:
        baseline = {
            "capturedAt": utc_now(),
            "controlPlane": control_plane_facts(),
            "dataPlane": data_plane_facts(client),
        }
    finally:
        client.close()

    print(f"\nCluster    : {baseline['controlPlane']['name']}")
    print(f"Type       : {baseline['controlPlane']['clusterType']}")
    print(f"Version    : {baseline['controlPlane']['mongoDBVersion']}")
    print(f"Disk (GB)  : {baseline['controlPlane']['diskSizeGB']}")
    print(f"Set        : {baseline['dataPlane']['setName']}")
    print(f"Members    : {len(baseline['dataPlane']['members'])}\n")

    header = f"  {'HOST':<55} {'STATE':<10} {'PRIO':>5} {'LAG (s)':>9}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for member in baseline["dataPlane"]["members"]:
        lag = member["lagSeconds"]
        lag_str = f"{lag:9.1f}" if lag is not None else f"{'-':>9}"
        print(
            f"  {member['host']:<55} {member['state']:<10} "
            f"{str(member['priority']):>5} {lag_str}"
        )
    print()

    write_json(artefact_path("baseline", "json"), baseline)


if __name__ == "__main__":
    main()
