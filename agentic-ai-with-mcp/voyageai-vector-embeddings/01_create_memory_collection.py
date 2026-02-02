#!/usr/bin/env python3
"""
Create the demo "memory" collection (and optional vector index) used by the agent.

Idempotent: safe to run multiple times.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING
from pymongo.errors import CollectionInvalid

# ---- config ----
DEFAULT_DB = "mcp_config"
DEFAULT_COLLECTION = "agent_memory"   # separate from mcp_config.investigations

load_dotenv()  # loads .env in the current working directory


def env(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if not v:
        raise SystemExit(f"Missing required env var: {name}")
    return v


def main() -> None:
    mongo_uri = env("MONGODB_URI")
    db_name = os.getenv("MEMORY_DB", DEFAULT_DB)
    coll_name = os.getenv("MEMORY_COLLECTION", DEFAULT_COLLECTION)

    client = MongoClient(mongo_uri)
    db = client[db_name]

    # Create collection if it doesn't exist
    if coll_name not in db.list_collection_names():
        try:
            db.create_collection(coll_name)
            print(f"Created collection: {db_name}.{coll_name}")
        except CollectionInvalid:
            pass

    coll = db[coll_name]

    # Suggested indexes for "agent memory"
    coll.create_index([("subject", ASCENDING)], name="subject_asc")
    coll.create_index([("created_at", ASCENDING)], name="created_at_asc")
    coll.create_index([("user_id", ASCENDING)], name="user_id_asc")

    # Seed a small doc so you can see it exists
    if coll.count_documents({}) == 0:
        coll.insert_one(
            {
                "user_id": "demo",
                "subject": "bootstrap",
                "memory": "This is the agent memory collection used for the MCP demo.",
                "created_at": datetime.now(timezone.utc),
            }
        )
        print("Inserted seed memory doc.")

    print("Done.")
    print(f"Collection ready: {db_name}.{coll_name}")


if __name__ == "__main__":
    main()
