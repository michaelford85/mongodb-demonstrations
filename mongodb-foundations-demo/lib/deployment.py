"""Read-only deployment introspection for the replica-set and HA sections.

Only non-mutating commands are used: `hello`, the driver's own topology and
option views, and `replSetGetStatus` / `replSetGetConfig` when the connected
user is authorized for them. Nothing here steps down a member or reconfigures
the set. Hostnames are shown; no credential, connection string, or secret is
ever read or printed.
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


def election_summary() -> dict:
    """Term and last-election facts from `replSetGetStatus`, when authorized."""
    try:
        status = get_client().admin.command("replSetGetStatus")
    except OperationFailure as exc:
        note = "Election detail needs additional privileges." \
            if exc.code == UNAUTHORIZED_CODE else str(exc)
        return {"authorized": False, "note": note}
    except PyMongoError as exc:
        return {"authorized": False, "note": str(exc)}

    primary = None
    elected_at = None
    for member in status.get("members", []):
        if member.get("stateStr") == "PRIMARY":
            primary = member.get("name")
            elected_at = member.get("electionDate")
    metrics = status.get("electionCandidateMetrics", {}) or {}
    return {
        "authorized": True,
        "term": status.get("term"),
        "primary": primary,
        "elected_at": elected_at,
        "election_reason": metrics.get("lastElectionReason", "not reported"),
        "majority_size": len(status.get("members", [])) // 2 + 1,
    }


def member_configuration() -> dict:
    """Per-member voting configuration from `replSetGetConfig`, when authorized.

    Priority, votes, and hidden are what actually decide which members can be
    elected and which count towards a majority.
    """
    try:
        config = get_client().admin.command("replSetGetConfig")["config"]
    except OperationFailure as exc:
        note = "Member configuration needs additional privileges " \
               "(for example the clusterMonitor role)." \
            if exc.code == UNAUTHORIZED_CODE else str(exc)
        return {"authorized": False, "note": note}
    except PyMongoError as exc:
        return {"authorized": False, "note": str(exc)}

    rows = []
    votes = 0
    for member in config.get("members", []):
        votes += member.get("votes", 0)
        rows.append({
            "member": member.get("host"),
            "priority": member.get("priority"),
            "votes": member.get("votes"),
            "hidden": bool(member.get("hidden", False)),
            "delay_s": member.get("secondaryDelaySecs",
                                  member.get("slaveDelay", 0)),
        })
    return {"authorized": True, "members": rows, "voting_members": votes,
            "majority_size": votes // 2 + 1}


def durability_settings() -> list:
    """What the driver in this app is configured to do, read from the client.

    Nothing here reads the connection string; these are the effective options
    the driver reports back.
    """
    try:
        options = get_client().options
    except PyMongoError:
        return []
    write_concern = options.write_concern.document or {"w": "server default"}
    return [
        {"setting": "write concern",
         "value": ", ".join("{}={}".format(k, v)
                            for k, v in write_concern.items()),
         "what it decides": "How many members must hold a write before it is "
                            "acknowledged. `majority` means an election cannot "
                            "lose it."},
        {"setting": "read concern",
         "value": str(options.read_concern.document or {}) or "server default",
         "what it decides": "How current, and how durable, the data a read "
                            "returns must be."},
        {"setting": "read preference",
         "value": options.read_preference.mongos_mode,
         "what it decides": "Which members a read may be served by. Primary "
                            "reads are the consistent default."},
        {"setting": "retryable writes",
         "value": str(bool(options.retry_writes)),
         "what it decides": "Whether the driver retries a write once after a "
                            "transient failure such as an election."},
        {"setting": "server selection timeout",
         "value": "{} ms".format(options.server_selection_timeout * 1000
                                 if options.server_selection_timeout else 0),
         "what it decides": "How long the driver waits for a suitable member "
                            "before giving up — the window an election has to "
                            "complete in."},
    ]
