#!/usr/bin/env python3
"""Deterministic sample-case evaluation from the command line.

Evaluates sample cases (or one ad-hoc case) against the ACTIVE configuration
snapshot. Uses MongoDB when MONGODB_URI is set; otherwise evaluates against
the seeded baseline fixture configuration in mock mode. Never calls an LLM.
"""

import argparse
import json
import os
import sys

from dotenv import find_dotenv, load_dotenv

from agent_change_ops_agent.evaluator import evaluate_case
from agent_change_ops_agent.fixtures import ALL_FIXTURES
from agent_change_ops_agent.store import DEMO_DATABASE_DEFAULT, create_store


def main() -> int:
    # Load .env BEFORE deriving environment-backed CLI defaults, so a value set
    # only in .env becomes the default for --database. load_dotenv() does not
    # override already-exported process environment variables, so precedence is:
    # explicit --database flag > exported MONGODB_DATABASE > .env > project default.
    # usecwd=True searches from the current working directory upward.
    load_dotenv(find_dotenv(usecwd=True))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-id", help="Evaluate a single ad-hoc case instead of all samples")
    parser.add_argument("--request-type", default="standard")
    parser.add_argument("--region", default="us-demo-1")
    parser.add_argument("--environment", default="prod")
    parser.add_argument("--workspace-id", default="demo_workspace_001")
    parser.add_argument("--database", default=os.environ.get("MONGODB_DATABASE", DEMO_DATABASE_DEFAULT))
    args = parser.parse_args()

    uri = os.environ.get("MONGODB_URI", "")
    store = create_store(uri, args.database)
    store.ensure_seeded()
    active = store.get_active_config()
    if not active:
        print("No active configuration found. Publish one through the agent first.")
        return 1

    print(
        f"Active configuration: {active['config_id']} v{active['config_version']} "
        f"[{store.mode.upper()} mode] — fictional demo data"
    )
    if args.service_id:
        cases = [
            {
                "case_id": "adhoc",
                "service_id": args.service_id,
                "request_type": args.request_type,
                "region": args.region,
                "environment": args.environment,
                "workspace_id": args.workspace_id,
            }
        ]
    else:
        cases = [d["data"] for d in store.list_sample_cases()] or ALL_FIXTURES["sample_cases"]

    for case in cases:
        result = evaluate_case(active, case)
        print(json.dumps({"case_id": case.get("case_id"), **result}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
