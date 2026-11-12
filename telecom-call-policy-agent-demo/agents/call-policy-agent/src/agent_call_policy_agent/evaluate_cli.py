#!/usr/bin/env python3
"""Deterministic call-control call evaluation from the command line.

Evaluates sample calls (or one --from-number) against the ACTIVE policy
snapshot. Uses MongoDB when MONGODB_URI is set; otherwise evaluates against
the seeded baseline fixture policy in mock mode. Never calls an LLM.
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv

from agent_call_policy_agent.evaluator import evaluate_call
from agent_call_policy_agent.fixtures import ALL_FIXTURES
from agent_call_policy_agent.store import DEMO_DATABASE_DEFAULT, create_store


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-number", help="Evaluate a single E.164 number instead of all samples")
    parser.add_argument("--carrier-id", default="demo_carrier_001")
    parser.add_argument("--origin-country", default="US")
    parser.add_argument("--enterprise-id", default="")
    parser.add_argument("--database", default=os.environ.get("MONGODB_DATABASE", DEMO_DATABASE_DEFAULT))
    args = parser.parse_args()

    load_dotenv()
    uri = os.environ.get("MONGODB_URI", "")
    store = create_store(uri, args.database)
    store.ensure_seeded()
    active = store.get_active_policy()
    if not active:
        print("No active policy found. Publish one through the agent first.")
        return 1

    print(f"Active policy: {active['policy_id']} v{active['policy_version']} "
          f"[{store.mode.upper()} mode] — fictional demo data")
    if args.from_number:
        calls = [{
            "call_id": "adhoc",
            "from_number": args.from_number,
            "carrier_id": args.carrier_id,
            "origin_country": args.origin_country,
            "enterprise_id": args.enterprise_id or None,
        }]
    else:
        calls = [d["data"] for d in store.list_sample_calls()] or ALL_FIXTURES["sample_calls"]

    for call in calls:
        result = evaluate_call(active, call)
        print(json.dumps({"call_id": call.get("call_id"), **result}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
