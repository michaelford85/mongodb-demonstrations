#!/usr/bin/env python3
"""Shard the Northstar Payments collections into per-region zones.

Turns the demo's collections into a GEOSHARDED topology: each collection is
sharded on a region-prefixed key, and each real region's key range is pinned to
the Atlas zone that owns that region's shard. Run this against the mongos SRV
string of a GEOSHARDED cluster (see .env.example) BEFORE seeding so every
insert routes to its home zone.

    python3 scripts/shard_collections.py           # shard + zone everything
    python3 scripts/shard_collections.py --status   # print current shard status

Idempotent: re-running skips collections that are already sharded and re-asserts
the same zone ranges. `merchants` is left unsharded (small reference data).
"""

import argparse
import sys
from pathlib import Path

# Allow running as `python3 scripts/shard_collections.py` from the demo root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from bson import MaxKey, MinKey  # noqa: E402
from pymongo.errors import OperationFailure  # noqa: E402

from lib.atlas_client import (REGION_ZONES, REGIONS, SHARD_KEYS,  # noqa: E402
                              UNIQUE_SHARD_KEYS, ZONE_BY_REGION, db_name,
                              get_client, get_db, is_collection_sharded,
                              is_mongos, shard_distribution)


def _errmsg(err: OperationFailure) -> str:
    return (err.details or {}).get("errmsg", str(err))


def _enable_sharding(client, name: str, verbose: bool) -> None:
    try:
        client.admin.command("enableSharding", name)
        if verbose:
            print(f"  ✓ Sharding enabled on database '{name}'")
    except OperationFailure as e:
        # Already enabled is not an error we care about — keep going.
        if verbose:
            print(f"  · enableSharding: {_errmsg(e)}")


def _shard_collection(client, name: str, coll: str, key: dict,
                      unique: bool, verbose: bool) -> None:
    ns = f"{name}.{coll}"
    try:
        client.admin.command("shardCollection", ns, key=key, unique=unique)
        if verbose:
            print(f"  ✓ Sharded {ns} on {key}" + (" (unique)" if unique else ""))
    except OperationFailure as e:
        # Most commonly: already sharded with this key — safe to skip.
        if verbose:
            print(f"  · {ns}: {_errmsg(e)}")


def _zone_ranges(client, name: str, coll: str, key: dict, verbose: bool) -> None:
    """Pin each region's key range to the Atlas zone that owns its shard."""
    ns = f"{name}.{coll}"
    second = list(key.keys())[1]  # the field after the "region" prefix
    for region in REGIONS:
        zone = ZONE_BY_REGION[region]
        lo = {"region": region, second: MinKey()}
        hi = {"region": region, second: MaxKey()}
        try:
            client.admin.command("updateZoneKeyRange", ns, min=lo, max=hi,
                                  zone=zone)
            if verbose:
                print(f"      region '{region}' -> {zone}")
        except OperationFailure as e:
            print(f"      WARN {ns} region '{region}' -> {zone}: {_errmsg(e)}")


def shard_all(client=None, name: str | None = None, verbose: bool = True) -> bool:
    """Shard + zone every collection in SHARD_KEYS. No-op off a mongos router.

    Returns True when sharding ran, False when skipped (not a sharded cluster).
    """
    client = client or get_client()
    name = name or db_name()
    if not is_mongos():
        if verbose:
            print("  · Not connected through a mongos router — skipping "
                  "sharding.\n    This demo expects a GEOSHARDED cluster; see "
                  ".env.example.")
        return False

    if verbose:
        print(f"Sharding '{name}' across {len(REGION_ZONES)} zones:")
        for z in REGION_ZONES:
            print(f"  {z['region']:8} → {z['zone']} ({z['atlas_region']})")
    _enable_sharding(client, name, verbose)
    for coll, key in SHARD_KEYS.items():
        _shard_collection(client, name, coll, key,
                          coll in UNIQUE_SHARD_KEYS, verbose)
        _zone_ranges(client, name, coll, key, verbose)
    if verbose:
        print("  · 'merchants' left unsharded (small reference data).")
        print("Sharding complete.")
    return True


def print_status(name: str | None = None) -> None:
    """Print per-collection shard status and per-shard document counts."""
    db = get_db()
    name = name or db_name()
    if not is_mongos():
        print("Not connected through a mongos router — no shard status to show.")
        return
    print(f"Shard status for '{name}':")
    for coll in SHARD_KEYS:
        sharded = is_collection_sharded(coll)
        dist = shard_distribution(coll)
        counts = ", ".join(f"{shard}={n}" for shard, n in sorted(dist.items()))
        flag = "sharded" if sharded else "UNSHARDED"
        print(f"  {coll:20} [{flag}]  {counts or '(no data)'}")
    print(f"  {'merchants':20} [reference]  "
          f"{shard_distribution('merchants').get('(unsharded)', 0)} docs")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Shard Northstar Payments collections into per-region zones")
    parser.add_argument("--status", action="store_true",
                        help="Print current shard status instead of sharding")
    args = parser.parse_args()
    if args.status:
        print_status()
    else:
        shard_all()
    get_client().close()


if __name__ == "__main__":
    main()
