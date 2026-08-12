"""Poll /status and print one line per second — the projector-friendly view.

    python app/watch.py
    python app/watch.py --url http://127.0.0.1:8000 --interval 1

Run this beside the service during an experiment. New topology events are
printed inline as they appear, so a primary change lands in the same scroll as
the latency it caused.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: E402

HEADER = (f"{'time':<8}  {'w ops/s':>7}  {'w avg':>7}  {'w p95':>7}  "
          f"{'r ops/s':>7}  {'r avg':>7}  {'err':>4}  {'err%':>5}  primary")


def _fmt(value, width: int = 7) -> str:
    return f"{'-':>{width}}" if value is None else f"{value:>{width}}"


def _primary(topology: dict) -> str:
    if "error" in topology:
        return f"?? {topology['error']}"
    primaries = [s["address"] for s in topology.get("servers", [])
                 if s["type"] == "RSPrimary"]
    return ", ".join(primaries) if primaries else "none visible"


def main() -> None:
    parser = argparse.ArgumentParser(description="Tail the /status endpoint.")
    parser.add_argument("--url", default=f"http://{config.HOST}:{config.PORT}",
                        help="base URL of the running service")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="seconds between polls (default: 1)")
    args = parser.parse_args()

    endpoint = args.url.rstrip("/") + "/status"
    seen_events = set()
    rows = 0

    # Stay readable when piped to a file or to tee during a workshop.
    sys.stdout.reconfigure(line_buffering=True)

    print(f"Polling {endpoint} every {args.interval}s. Ctrl-C to stop.\n")
    while True:
        try:
            with urllib.request.urlopen(endpoint, timeout=5) as response:
                payload = json.load(response)
        except (urllib.error.URLError, OSError) as exc:
            print(f"{time.strftime('%H:%M:%S'):<8}  service unreachable: "
                  f"{type(exc).__name__}")
            time.sleep(args.interval)
            continue

        if rows % 20 == 0:
            print(HEADER)
        rows += 1

        window = payload["window"]
        write, read = window["write"], window["read"]
        print(
            f"{time.strftime('%H:%M:%S'):<8}  "
            f"{_fmt(write['ops_per_second'])}  {_fmt(write['avg_latency_ms'])}  "
            f"{_fmt(write['p95_latency_ms'])}  "
            f"{_fmt(read['ops_per_second'])}  {_fmt(read['avg_latency_ms'])}  "
            f"{window['errors']:>4}  "
            f"{window['error_rate'] * 100:>4.1f}%  "
            f"{_primary(payload.get('topology', {}))}"
        )

        for event in reversed(payload.get("topology_events", [])):
            key = (event["at"], event["event"], event["detail"])
            if key not in seen_events:
                seen_events.add(key)
                print(f"          >> {event['event']}: {event['detail']}")

        last = payload.get("last_error")
        if last:
            key = ("error", last["at"])
            if key not in seen_events:
                seen_events.add(key)
                print(f"          !! {last['kind']} error: {last['type']}")

        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
