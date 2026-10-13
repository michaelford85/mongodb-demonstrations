"""Replica set state watcher — the topology-side evidence for every test case.

Polls `hello` twice a second and prints a line only when something changes:
the primary moves, a member changes state, or the set has no primary. The
"no primary" intervals are the observed election windows; combined with
writer.py output they separate election time from client recovery time.

    python3 watcher.py --label t3-failover-idle

Artefacts: results/watcher-<label>-<timestamp>.jsonl
"""

from __future__ import annotations

import argparse
import signal
import sys
import time

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from common import (STATE_NAMES, append_jsonl, artefact_path, load_env,
                    scoped_uri, utc_now)

POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 30.0


def member_states(client: MongoClient) -> dict[str, str]:
    """Best-effort per-member state map; empty if the command is unavailable."""
    try:
        status = client.admin.command("replSetGetStatus")
    except PyMongoError:
        return {}
    return {
        m["host"]: STATE_NAMES.get(m["state"], str(m["state"]))
        for m in status.get("members", [])
    }


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Replica set state watcher")
    parser.add_argument("--label", required=True,
                        help="Test case label, used in the artefact filename")
    args = parser.parse_args()

    # clusterMonitor is enough here — the watcher never touches data.
    uri = scoped_uri("MONITOR_CLUSTER_URI")
    client = MongoClient(uri, serverSelectionTimeoutMS=2000)

    log = artefact_path(f"watcher-{args.label}", "jsonl")
    print(f"Watcher polling hello() every {POLL_SECONDS}s")
    print(f"Log -> {log}")
    print("Stop with Ctrl+C once the test case is complete.\n")

    outages: list[float] = []

    def handle_sigint(_sig, _frame):
        print("\n--- watcher summary ---")
        if outages:
            print(f"  intervals with no primary : {len(outages)}")
            print(f"  longest                   : {max(outages):.1f} s")
            print(f"  total                     : {sum(outages):.1f} s")
        else:
            print("  intervals with no primary : none observed")
        print("-----------------------\n")
        client.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    last_primary: str | None = None
    last_states: dict[str, str] = {}
    last_print = 0.0
    no_primary_since: float | None = None

    while True:
        now = time.monotonic()
        record: dict = {"ts": utc_now()}
        try:
            info = client.admin.command("hello")
            primary = info.get("primary")
            states = member_states(client)

            if primary is None and no_primary_since is None:
                no_primary_since = now
            elif primary is not None and no_primary_since is not None:
                duration = now - no_primary_since
                outages.append(duration)
                print(f"  {utc_now():%H:%M:%S}  ELECTED   after {duration:.1f}s "
                      f"with no primary -> {primary}")
                append_jsonl(log, {"ts": utc_now(), "event": "elected",
                                   "noPrimarySeconds": round(duration, 2),
                                   "primary": primary})
                no_primary_since = None

            changed = primary != last_primary or states != last_states
            if changed or now - last_print > HEARTBEAT_SECONDS:
                tag = "CHANGE" if changed else "      "
                print(f"  {utc_now():%H:%M:%S}  {tag}    set={info.get('setName')}  "
                      f"primary={primary or '(none)'}  "
                      f"states={sorted(set(states.values()))}")
                record.update({
                    "event": "state",
                    "setName": info.get("setName"),
                    "primary": primary,
                    "members": states,
                })
                append_jsonl(log, record)
                last_primary, last_states, last_print = primary, states, now
        except PyMongoError as exc:
            if no_primary_since is None:
                no_primary_since = now
            if now - last_print > 1.0:
                print(f"  {utc_now():%H:%M:%S}  ERROR     {type(exc).__name__}")
                record.update({"event": "error", "error": type(exc).__name__})
                append_jsonl(log, record)
                last_print = now

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
