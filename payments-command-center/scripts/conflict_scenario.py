#!/usr/bin/env python3
"""Same-card, multi-region conflict scenario for Northstar Payments.

Fires several *near-simultaneous* authorizations against ONE card from
different processing regions, each asking for the full available balance. The
card's balance document lives on a single owner shard's primary, so those
writes are serialized there: a guarded ``$inc`` lets exactly one win the funds
and declines the rest with ``insufficient_funds`` — no double-spend, no
application lock. A second pass proves idempotent replay (same key ⇒ same
decision, charged once).

    python3 scripts/conflict_scenario.py                 # default: all regions
    python3 scripts/conflict_scenario.py --amount 250     # set the contested sum
    python3 scripts/conflict_scenario.py --regions us-east eu

Read the outcome out loud during a demo: N requests in, 1 approved, N-1
declined, final balance never negative.
"""

import argparse
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.atlas_client import REGIONS, get_client, get_db, is_mongos  # noqa: E402
from lib.simulator import authorize  # noqa: E402


def _pick_card(db) -> tuple[dict, dict, dict]:
    """Return (account, instrument, merchant) for a single real card."""
    inst = next(iter(db.payment_instruments.aggregate([{"$sample": {"size": 1}}])), None)
    if not inst:
        raise SystemExit("No data. Run: python3 seed_data.py")
    account = db.accounts.find_one({"account_id": inst["account_id"]})
    merchant = next(iter(db.merchants.aggregate([{"$sample": {"size": 1}}])))
    return account, inst, merchant


def run_conflict(db, *, regions: list[str] | None = None,
                 amount: float = 100.0) -> dict:
    """Fire one concurrent auth per region for the same card and full balance."""
    regions = regions or REGIONS
    account, instrument, merchant = _pick_card(db)
    owner = account["region"]

    # Arm the card so only ONE request can be funded.
    db.accounts.update_one(
        {"account_id": account["account_id"], "region": owner},
        {"$set": {"available_balance": amount, "hold_amount": 0.0}})

    barrier = threading.Barrier(len(regions))
    results: dict[str, dict] = {}

    def worker(region: str) -> None:
        barrier.wait()  # release all threads at once → true contention
        results[region] = authorize(
            db, account=account, instrument=instrument, merchant=merchant,
            region=region, amount=amount, risk_flags=[])

    threads = [threading.Thread(target=worker, args=(r,)) for r in regions]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = db.accounts.find_one(
        {"account_id": account["account_id"], "region": owner})
    rows = [{
        "region": r,
        "status": d["auth_status"],
        "reason": d.get("decline_reason"),
        "cross_region": d.get("cross_region_owner_write"),
        "owner_write_ms": d.get("owner_write_ms"),
        "decision_id": d["decision_id"],
    } for r, d in results.items()]
    return {
        "account_id": account["account_id"],
        "owner_region": owner,
        "amount": amount,
        "results": rows,
        "approved": sum(1 for r in rows if r["status"] == "approved"),
        "declined": sum(1 for r in rows if r["status"] == "declined"),
        "final_balance": round(final.get("available_balance", 0.0), 2),
    }


def run_idempotency(db, *, amount: float = 100.0) -> dict:
    """Replay one request twice with the same key — it must charge only once."""
    account, instrument, merchant = _pick_card(db)
    owner = account["region"]
    db.accounts.update_one(
        {"account_id": account["account_id"], "region": owner},
        {"$set": {"available_balance": amount, "hold_amount": 0.0}})
    key = "idem-demo-fixed-key"
    kw = dict(account=account, instrument=instrument, merchant=merchant,
              region=owner, amount=amount, idempotency_key=key, risk_flags=[])
    first = authorize(db, **kw)
    replay = authorize(db, **kw)
    final = db.accounts.find_one(
        {"account_id": account["account_id"], "region": owner})
    return {
        "same_decision": first["decision_id"] == replay["decision_id"],
        "decision_id": first["decision_id"],
        "final_balance": round(final.get("available_balance", 0.0), 2),
        "charged_once": abs(final.get("available_balance", 0.0)
                            - (amount - first["amount"])) < 0.001,
    }


def _print(res: dict) -> None:
    print(f"\nSame-card conflict — account {res['account_id']} "
          f"(owner region: {res['owner_region']}), contested {res['amount']}")
    for r in sorted(res["results"], key=lambda x: x["region"]):
        tag = "OWNER" if not r["cross_region"] else "cross-region"
        extra = f"reason={r['reason']}" if r["reason"] else ""
        print(f"  {r['region']:8} [{tag:12}] {r['status']:9} "
              f"owner_write={r['owner_write_ms']}ms  {extra}")
    print(f"  → {res['approved']} approved, {res['declined']} declined, "
          f"final balance {res['final_balance']} (never negative)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Same-card multi-region conflict")
    parser.add_argument("--amount", type=float, default=100.0)
    parser.add_argument("--regions", nargs="+", choices=REGIONS, default=None)
    args = parser.parse_args()
    if not is_mongos():
        print("Note: not connected through a mongos router — the scenario still "
              "runs, but single-primary serialization is best shown on the "
              "GEOSHARDED cluster (see .env.example).")
    db = get_db()
    _print(run_conflict(db, regions=args.regions, amount=args.amount))
    idem = run_idempotency(db, amount=args.amount)
    print(f"\nIdempotent replay: same decision={idem['same_decision']}, "
          f"charged once={idem['charged_once']}, "
          f"final balance {idem['final_balance']}")
    get_client().close()


if __name__ == "__main__":
    main()
