"""Pre-flight check 1 — server version, FCV, and topology.

Answers: what am I actually connected to, and is the feature compatibility
version pinned somewhere that would block or stall an upgrade?

Read-only. Prints a block you can paste straight into upgrade notes.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pymongo.errors import OperationFailure, PyMongoError  # noqa: E402

from _common import (  # noqa: E402
    footer,
    get_client,
    header,
    kv,
    note,
    ok,
    section,
    version_tuple,
    warn,
)


def _build_info() -> dict:
    return get_client().admin.command("buildInfo")


def _fcv() -> str:
    """Read the FCV. Not exposed on Atlas shared/flex tiers, so degrade nicely."""
    try:
        result = get_client().admin.command(
            {"getParameter": 1, "featureCompatibilityVersion": 1}
        )
        return str(result["featureCompatibilityVersion"]["version"])
    except (OperationFailure, KeyError):
        return "unavailable"


def _topology() -> dict:
    hello = get_client().admin.command("hello")
    return {
        "type": "sharded" if hello.get("msg") == "isdbgrid" else "replica set",
        "set_name": hello.get("setName", "n/a"),
        "primary": hello.get("primary", "n/a"),
        "hosts": hello.get("hosts", []),
        "max_wire_version": hello.get("maxWireVersion"),
    }


def run() -> list:
    findings = []
    build = _build_info()
    server = build["version"]
    server_parts = version_tuple(server)
    fcv = _fcv()
    topo = _topology()

    header("Check 1 — server version, FCV, and topology")

    section("Server")
    kv("server version", server)
    kv("feature compatibility ver", fcv)
    kv("storage engine", ", ".join(build.get("storageEngines", [])) or "unknown")
    kv("javascript engine", build.get("javascriptEngine", "unknown"))
    kv("max wire version", topo["max_wire_version"])

    section("Topology")
    kv("deployment type", topo["type"])
    kv("replica set name", topo["set_name"])
    kv("primary", topo["primary"])
    kv("voting/data hosts", len(topo["hosts"]))
    for host in topo["hosts"]:
        print(f"      {host}")

    section("Readiness")
    if server_parts >= (8, 0):
        ok(f"server is already {server}; this is a post-upgrade verification run")
        if fcv != "unavailable" and version_tuple(fcv) < (8, 0):
            findings.append(
                f"server is {server} but FCV is still {fcv} — 8.0 features stay "
                f"disabled and downgrade is still possible until FCV is raised"
            )
            warn(findings[-1])
        elif fcv != "unavailable":
            ok(f"FCV is {fcv}; 8.0 behaviour and features are active")
    else:
        note(f"server is {server}; target for this checklist is 8.0")
        if fcv != "unavailable" and version_tuple(fcv) < server_parts[:2]:
            findings.append(
                f"FCV {fcv} lags the server version {server} — raise FCV to "
                f"{'.'.join(str(p) for p in server_parts[:2])} and let it settle "
                f"before starting the 8.0 upgrade"
            )
            warn(findings[-1])
        else:
            ok("FCV matches the server version; the usual precondition is met")

    if fcv == "unavailable":
        note(
            "FCV is not readable with these credentials or on this tier; check "
            "it in the Atlas UI or with a user that has the required privileges"
        )

    section("Paste-ready line")
    print(f"  server={server} fcv={fcv} type={topo['type']} "
          f"set={topo['set_name']} nodes={len(topo['hosts'])}")

    footer(findings)
    return findings


def main() -> None:
    argparse.ArgumentParser(
        description="Report server version, FCV, and topology (read-only)."
    ).parse_args()
    try:
        run()
    except PyMongoError as exc:
        sys.exit(f"Could not query the cluster: {exc}")


if __name__ == "__main__":
    main()
