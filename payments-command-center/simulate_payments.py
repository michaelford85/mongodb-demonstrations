"""Continuously write synthetic authorization events into Atlas.

Run this in a second terminal while the Streamlit app is open. The dashboard
picks up new events in near real time (via change streams, with a polling
fallback). Use the flags to drive the two storytelling modes:

    python3 simulate_payments.py                  # steady normal traffic
    python3 simulate_payments.py --burst          # high-volume burst mode
    python3 simulate_payments.py --impair eu-west # region impairment / reroute

Stop with Ctrl+C.
"""

import argparse
import signal
import sys
import time

from lib.atlas_client import (REGIONS, batch_size, db_name, default_region,
                              get_db, is_empty)
from lib.simulator import generate_event, take_snapshot


def _print_decision(d: dict) -> None:
    status = d["auth_status"].upper()
    reroute = f"  reroute:{d['routing_region']}" if d.get("failover_reason") else ""
    flags = f"  flags:{','.join(d['risk_flags'])}" if d.get("risk_flags") else ""
    print(f"  [{status:8}] {d['payment_type']:13} {d['currency']} "
          f"{d['amount']:>8.2f}  {d['region']:12} {d['merchant_name']}{reroute}{flags}")


def run(burst: bool, impaired_region: str | None, interval: float) -> None:
    db = get_db()
    if is_empty():
        print("No seed data found. Run: python3 seed_data.py")
        sys.exit(1)

    per_tick = batch_size() * (5 if burst else 1)
    mode = "BURST" if burst else "NORMAL"
    print(f"Simulator connected to {db_name()} (home region: {default_region()})")
    print(f"Mode: {mode} — {per_tick} events / tick"
          + (f" — impairing {impaired_region}" if impaired_region else ""))
    print("Press Ctrl+C to stop.\n")

    def handle_sigint(sig, frame):
        print("\nSimulator stopped.")
        take_snapshot(db)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    tick = 0
    while True:
        for _ in range(per_tick):
            decision = generate_event(db, impaired_region=impaired_region)
            _print_decision(decision)
        tick += 1
        # Refresh balance snapshots periodically so the account view stays current.
        if tick % 10 == 0:
            take_snapshot(db)
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Northstar Payments event simulator")
    parser.add_argument("--burst", action="store_true",
                        help="High-volume burst mode (5x batch size per tick)")
    parser.add_argument("--impair", choices=REGIONS, metavar="REGION",
                        help="Impair a region and reroute its traffic")
    parser.add_argument("--interval", type=float, default=1.5,
                        help="Seconds between ticks (default: 1.5)")
    args = parser.parse_args()
    run(args.burst, args.impair, args.interval)


if __name__ == "__main__":
    main()
