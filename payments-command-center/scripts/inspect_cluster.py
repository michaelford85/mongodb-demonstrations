#!/usr/bin/env python3
"""Pretty-print the Northstar Payments GEOSHARDED cluster status.

Read-only introspection of the live cluster: the shards and their zones, the
config server replica set, the region -> zone pinning, and how each collection's
chunks and documents are distributed across shards. Run against the mongos
router configured in .env (no credentials are passed on the command line).

    python3 scripts/inspect_cluster.py
"""

import sys
from pathlib import Path

# Allow running as `python3 scripts/inspect_cluster.py` from the demo root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.atlas_client import (REGION_ZONES, SHARD_KEYS,  # noqa: E402
                              UNIQUE_SHARD_KEYS, ZONE_BY_REGION, db_name,
                              get_client, get_db, is_collection_sharded,
                              is_mongos, region_distribution)


def header(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def show_shards(client) -> None:
    header("1. Shards (host, state, zones)")
    try:
        shards = client.admin.command("listShards")["shards"]
    except Exception as e:
        print(f"  listShards unavailable: {type(e).__name__}: {e}")
        return
    for s in sorted(shards, key=lambda x: x["_id"]):
        tags = ", ".join(s.get("tags", [])) or "(no zone)"
        print(f"  {s['_id']:26} state={s.get('state')}  zones=[{tags}]")
        print(f"      {s.get('host', '')[:96]}")


def show_config_server(client) -> None:
    header("2. Config server replica set")
    try:
        cfg = client.admin.command("getShardMap").get("map", {}).get("config")
        print(f"  {cfg}" if cfg else "  (config entry not exposed here)")
    except Exception as e:
        print(f"  getShardMap unavailable ({type(e).__name__}); see Shards above.")


def show_zone_map() -> None:
    header("3. Region -> zone pinning")
    print(f"  {'region':10} {'atlas region':14} zone")
    for z in REGION_ZONES:
        print(f"  {z['region']:10} {z['atlas_region']:14} {z['zone']}")


def show_distribution(db) -> None:
    header("4. Per-collection region distribution (routed) & owning zone")
    for coll in SHARD_KEYS:
        key = ", ".join(SHARD_KEYS[coll])
        uniq = " (unique)" if coll in UNIQUE_SHARD_KEYS else ""
        flag = "sharded" if is_collection_sharded(coll) else "UNSHARDED"
        total = db[coll].count_documents({})
        print(f"\n  {coll}  [{flag}]  key={{{key}}}{uniq}")
        print(f"    documents (routed count): {total}")
        for region, n in region_distribution(coll).items():
            zone = ZONE_BY_REGION.get(region, "?")
            print(f"      {region:8} -> {zone:8} {n}")
    m = db["merchants"].count_documents({})
    print(f"\n  merchants  [reference, unsharded]  documents: {m}")


def show_chunks(client) -> None:
    header("5. Chunk counts per shard (config.chunks)")
    name = db_name()
    try:
        rows = list(client["config"].chunks.aggregate([
            {"$lookup": {"from": "collections", "localField": "uuid",
                         "foreignField": "uuid", "as": "c"}},
            {"$unwind": "$c"},
            {"$match": {"c._id": {"$regex": f"^{name}\\."}}},
            {"$group": {"_id": {"ns": "$c._id", "shard": "$shard"},
                        "chunks": {"$sum": 1}}},
            {"$sort": {"_id.ns": 1, "_id.shard": 1}},
        ]))
    except Exception as e:
        print(f"  config.chunks not readable ({type(e).__name__}); "
              "needs an atlasAdmin-level user.")
        return
    if not rows:
        print("  (no chunk metadata visible for this database)")
        return
    for r in rows:
        print(f"  {r['_id']['ns']:42} {r['_id']['shard']:28} "
              f"chunks={r['chunks']}")


def main() -> None:
    client = get_client()
    db = get_db()
    print(f"Database: {db_name()}")
    if not is_mongos():
        print("WARNING: not connected through a mongos router — this is not a "
              "sharded cluster, so most sections below will be empty.")
    show_shards(client)
    show_config_server(client)
    show_zone_map()
    show_distribution(db)
    show_chunks(client)
    print("\nNote: this is an Atlas Global Cluster (GEOSHARDED / Global Writes). "
          "Atlas manages\nphysical chunk placement and reconciles zone key "
          "ranges, so section 5's chunks may\nsit on the primary shard rather "
          "than each region's owner shard. The region ->\nzone ownership "
          "(section 3) and the routed per-region counts (section 4) are the\n"
          "authoritative, stable view of locality — they route by shard key and "
          "are unaffected\nby physical placement or migration orphans.")
    client.close()


if __name__ == "__main__":
    main()
