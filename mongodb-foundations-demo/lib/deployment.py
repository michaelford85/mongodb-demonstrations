"""Read-only deployment introspection for the replica-set section.

Only non-mutating commands are used: `hello`, the driver's own topology view,
and `replSetGetStatus` when the connected user is authorized for it. Hostnames
are shown; no credential, connection string, or secret is ever read or printed.
"""

from __future__ import annotations

from pymongo.errors import OperationFailure, PyMongoError

from lib.mongo_client import get_client

UNAUTHORIZED_CODE = 13

SHARDING_CALLOUT = (
    "This demo runs on a non-sharded replica set. In a sharded deployment, "
    "data is distributed across shards; each shard is commonly implemented as "
    "a replica set."
)


def hello_summary() -> dict:
    """Deployment identity and role from the `hello` command."""
    try:
        hello = get_client().admin.command("hello")
    except PyMongoError as exc:
        return {"ok": False, "error": str(exc)}
    if hello.get("isWritablePrimary"):
        role = "PRIMARY"
    elif hello.get("secondary"):
        role = "SECONDARY"
    elif hello.get("msg") == "isdbgrid":
        role = "ROUTER"
    else:
        role = "not reported"
    return {
        "ok": True,
        "replica_set": hello.get("setName", "not reported"),
        "connected_member": hello.get("me", "not reported"),
        "connected_member_role": role,
        "primary": hello.get("primary", "not reported"),
        "members_reported": hello.get("hosts", []),
        "read_only": hello.get("readOnly", False),
    }


def topology_rows() -> list:
    """The driver's own view of each known server. Needs no extra privilege."""
    try:
        client = get_client()
        client.admin.command("ping")
        description = client.topology_description
    except PyMongoError:
        return []
    rows = []
    for server in description.server_descriptions().values():
        host, port = server.address
        rows.append({
            "host": "{}:{}".format(host, port),
            "role_seen_by_driver": server.server_type_name,
            "round_trip_ms": round((server.round_trip_time or 0) * 1000, 1),
        })
    return sorted(rows, key=lambda r: r["host"])


def replset_status() -> dict:
    """Member status from `replSetGetStatus`, or a clear authorization note."""
    try:
        status = get_client().admin.command("replSetGetStatus")
    except OperationFailure as exc:
        if exc.code == UNAUTHORIZED_CODE:
            return {"authorized": False,
                    "note": "Detailed member status requires additional "
                            "privileges (for example the clusterMonitor role). "
                            "Falling back to `hello` and driver metadata."}
        return {"authorized": False,
                "note": "replSetGetStatus was refused: {}".format(exc)}
    except PyMongoError as exc:
        return {"authorized": False,
                "note": "replSetGetStatus unavailable: {}".format(exc)}

    primary_optime = None
    for member in status.get("members", []):
        if member.get("stateStr") == "PRIMARY":
            primary_optime = member.get("optimeDate")

    rows = []
    for member in status.get("members", []):
        lag = None
        optime = member.get("optimeDate")
        if primary_optime is not None and optime is not None:
            lag = round((primary_optime - optime).total_seconds(), 1)
        rows.append({
            "member": member.get("name"),
            "state": member.get("stateStr"),
            "health": member.get("health"),
            "replication_lag_s": lag,
            "last_heartbeat_ok": member.get("lastHeartbeatMessage", "") == "",
        })
    return {"authorized": True,
            "replica_set": status.get("set"),
            "members": rows}
