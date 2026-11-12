#!/usr/bin/env python3
"""Reset the call-control demo data.

Mongo mode: drops ONLY the demo collections in the demo database, then
re-seeds synthetic fixtures on next use. Requires --yes as a double gate.

Mock mode: nothing is persisted, so there is nothing to reset.

Never touches any other database or collection.
"""

import argparse
import os
import sys

from dotenv import load_dotenv

from agent_call_policy_agent.store import DEMO_DATABASE_DEFAULT, create_store


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="Confirm the demo-data reset")
    parser.add_argument("--database", default=os.environ.get("MONGODB_DATABASE", DEMO_DATABASE_DEFAULT))
    args = parser.parse_args()

    load_dotenv()
    uri = os.environ.get("MONGODB_URI", "")
    if not uri:
        print("Mock mode (MONGODB_URI empty): in-memory data is not persisted; nothing to reset.")
        return 0

    if not args.yes:
        print(f"Refusing to reset demo data in MongoDB database {args.database!r} without --yes.")
        return 1

    store = create_store(uri, args.database)
    store.clear_demo_data()
    print(f"Dropped demo collections in database {args.database!r}.")
    print("Synthetic fixtures re-seed automatically on next use.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
