"""Shared MongoDB Atlas connection helpers for Northstar Payments Command Center.

A single cached client is reused across the app, the seed script, and the
simulator. Collection names live here so every module agrees on the schema.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv(Path(__file__).parent.parent / ".env")

DEFAULT_DB_NAME = "northstar_payments"

# Real Atlas regions this demo is provisioned across. The demo runs on a
# GEOSHARDED cluster where each shard lives in its own zone; Atlas names zones
# "Zone 1", "Zone 2", ... in the order shards appear in CLUSTER_SHARDS. The
# ORDER below must therefore match the CLUSTER_SHARDS order used when
# provisioning ../atlas-sharded-cluster-provisioning.
REGION_ZONES = [
    {"region": "us-east", "atlas_region": "US_EAST_1", "zone": "Zone 1"},
    {"region": "us-west", "atlas_region": "US_WEST_2", "zone": "Zone 2"},
    {"region": "eu",      "atlas_region": "EU_WEST_1", "zone": "Zone 3"},
]

# Region identifiers used across seed data, the simulator, and the dashboard.
REGIONS = [z["region"] for z in REGION_ZONES]
ZONE_BY_REGION = {z["region"]: z["zone"] for z in REGION_ZONES}
ATLAS_REGION_BY_REGION = {z["region"]: z["atlas_region"] for z in REGION_ZONES}

# The three payment event shapes the demo tells a story around.
PAYMENT_TYPES = ["card_present", "wallet_token", "installment"]

# Logical collections that make up the authorization workload.
COLLECTIONS = [
    "accounts",
    "payment_instruments",
    "merchants",
    "auth_requests",
    "auth_decisions",
    "ledger_events",
    "balance_snapshots",
]

# Shard-key plan. Account-scoped collections are zoned by the account's OWNER
# region so a card's balance document is region-local and owned by a single
# primary (the anchor that serializes same-card writes). The journals are zoned
# by the PROCESSING region so each region writes locally, while mongos still
# serves one logical, cross-region-visible collection. `merchants` is small
# reference data and is left unsharded on the primary shard.
#
# Every shard key is region-prefixed so each range maps cleanly to one zone.
# On a sharded collection a unique index must be prefixed by the full shard
# key, so the shard key IS the uniqueness guarantee where we need one:
#   accounts        -> one balance doc per (region, account_id)
#   auth_requests   -> one request per (region, idempotency_key)  [exactly-once]
#   auth_decisions  -> one decision per (region, request_id)
SHARD_KEYS = {
    "accounts":            {"region": 1, "account_id": 1},
    "payment_instruments": {"region": 1, "account_id": 1},
    "balance_snapshots":   {"region": 1, "account_id": 1},
    "auth_requests":       {"region": 1, "idempotency_key": 1},
    "auth_decisions":      {"region": 1, "request_id": 1},
    "ledger_events":       {"region": 1, "event_id": 1},
}

# Shard keys that are enforced unique (the index shardCollection builds is made
# unique). These double as the collection's uniqueness constraint.
UNIQUE_SHARD_KEYS = {"accounts", "auth_requests", "auth_decisions"}

_client: MongoClient | None = None


def get_client() -> MongoClient:
    """Return a cached MongoClient built from MONGODB_URI.

    Writes use w:"majority" (RPO 0 — a write is acknowledged only after a
    majority of a shard's replica-set members have it). retryWrites lets the
    driver ride out an election without surfacing an error to the app.
    """
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise ValueError(
                "Missing MONGODB_URI. Copy .env.example to .env and set your "
                "Atlas connection string."
            )
        _client = MongoClient(uri, serverSelectionTimeoutMS=10_000,
                              w="majority", retryWrites=True)
    return _client


def get_db() -> Database:
    """Return the demo database handle."""
    db_name = os.getenv("MONGODB_DB_NAME", DEFAULT_DB_NAME)
    return get_client()[db_name]


def db_name() -> str:
    return os.getenv("MONGODB_DB_NAME", DEFAULT_DB_NAME)


def default_region() -> str:
    return os.getenv("SIMULATION_DEFAULT_REGION", REGIONS[0])


def batch_size() -> int:
    return int(os.getenv("SIMULATION_BATCH_SIZE", "4"))


def is_empty() -> bool:
    """True when the core collections have not been seeded yet."""
    db = get_db()
    return db.accounts.count_documents({}, limit=1) == 0


def supports_change_streams() -> bool:
    """Change streams need a replica set. Atlas always qualifies, but a local
    standalone does not — this lets the UI fall back to polling gracefully."""
    try:
        client = get_client()
        hello = client.admin.command("hello")
        return bool(hello.get("setName")) or hello.get("msg") == "isdbgrid"
    except Exception:
        return False


def is_mongos() -> bool:
    """True when connected through a sharded cluster's mongos router."""
    try:
        return get_client().admin.command("hello").get("msg") == "isdbgrid"
    except Exception:
        return False


def zone_for_region(region: str) -> str | None:
    """Atlas zone name that owns a given demo region (e.g. 'us-east' -> 'Zone 1')."""
    return ZONE_BY_REGION.get(region)


def is_collection_sharded(coll_name: str) -> bool:
    """True when the given collection is sharded across the cluster.

    Uses collStats, which through mongos reports a top-level ``sharded`` flag
    (and a per-shard ``shards`` breakdown) for sharded collections.
    """
    try:
        stats = get_db().command("collStats", coll_name)
    except Exception:
        return False
    return bool(stats.get("sharded")) or bool(stats.get("shards"))


def shard_distribution(coll_name: str) -> dict[str, int]:
    """Per-shard document counts for a collection, via collStats (allowed on
    Atlas). Returns {shard_name: count}; a single '(unsharded)' entry means the
    collection still lives entirely on the primary shard."""
    try:
        stats = get_db().command("collStats", coll_name)
    except Exception:
        return {}
    shards = stats.get("shards") or {}
    if not shards:
        return {"(unsharded)": stats.get("count", 0)}
    return {name: s.get("count", 0) for name, s in shards.items()}


def region_distribution(coll_name: str) -> dict[str, int]:
    """Routed document counts per demo region for a collection.

    Counts are targeted on the ``region`` shard-key prefix, so they reflect the
    logical home zone of every document — the authoritative, stable view of
    locality. Unlike raw $collStats per-shard counts, these are unaffected by
    Atlas Global Writes managing physical chunk placement (which can leave data
    on the primary shard) or by orphaned docs from in-flight migrations."""
    db = get_db()
    try:
        return {r: db[coll_name].count_documents({"region": r}) for r in REGIONS}
    except Exception:
        return {}
