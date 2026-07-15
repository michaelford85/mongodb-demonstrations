"""Authorization event generation for Northstar Payments.

A single call to ``generate_event`` produces one coherent authorization: an
``auth_requests`` document (whose payload shape varies by payment type), a
denormalized ``auth_decisions`` document for fast feed reads, and one or more
``ledger_events``. Account balances and holds are updated in place. This same
function backfills seed history and drives the live simulator.
"""

import random
import uuid
from datetime import datetime, timezone

from pymongo.database import Database

from lib.atlas_client import REGIONS
from lib.sample_data import CURRENCIES, RISK_FLAGS

# Regions that "route away" to a partner region during impairment storytelling.
FAILOVER_MAP = {
    "us-east": "us-west",
    "eu-west": "us-east",
    "ap-southeast": "us-west",
    "sa-east": "us-east",
    "us-west": "us-east",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_payload(payment_type: str, amount: float, currency: str) -> dict:
    """Return a payment-type-specific payload — the flexible-schema story."""
    if payment_type == "card_present":
        return {
            "entry_mode": random.choice(["chip", "contactless", "swipe"]),
            "terminal_id": f"POS-{random.randint(1000, 9999)}",
            "pos_country": random.choice(["US", "GB", "SG", "BR", "DE"]),
        }
    if payment_type == "wallet_token":
        return {
            "device_id": "dev_" + uuid.uuid4().hex[:12],
            "wallet_cryptogram": uuid.uuid4().hex[:16],
            "tokenized": True,
        }
    # installment / split tender
    months = random.choice([3, 6, 12])
    return {
        "plan_months": months,
        "installment_amount": round(amount / months, 2),
        "tender_split": [
            {"method": "installment_plan", "amount": round(amount * 0.7, 2)},
            {"method": "wallet_balance", "amount": round(amount * 0.3, 2)},
        ],
    }


def _decide(amount: float, risk_flags: list[str], available: float) -> tuple[str, str | None]:
    """Simple, explainable decision logic — good for narrating live."""
    if amount > available:
        return "declined", "insufficient_funds"
    if "merchant_watchlist" in risk_flags or len(risk_flags) >= 3:
        return "declined", "risk_hold"
    if len(risk_flags) == 2 and random.random() < 0.4:
        return "pending", "manual_review"
    return "approved", None


def generate_event(db: Database, *, region: str | None = None,
                   impaired_region: str | None = None,
                   at: datetime | None = None) -> dict:
    """Create one full authorization and persist it. Returns the decision doc."""
    account = _random_account(db)
    instrument = _random_instrument(db, account["account_id"])
    merchant = _random_merchant(db)

    region = region or account["region"]
    currency = CURRENCIES.get(region, "USD")
    payment_type = instrument["payment_type"]
    amount = round(random.uniform(4.0, min(account["available_balance"] + 50, 900)), 2)
    ts = at or _now()

    # Region impairment storytelling: route away and annotate the reason.
    routing_region, failover_reason = region, None
    if impaired_region and region == impaired_region:
        routing_region = FAILOVER_MAP.get(region, "us-west")
        failover_reason = f"{region}_impaired_rerouted_to_{routing_region}"

    risk_flags = random.sample(RISK_FLAGS, k=random.choices([0, 1, 2, 3],
                               weights=[62, 24, 10, 4])[0])
    status, reason = _decide(amount, risk_flags, account["available_balance"])
    latency_ms = random.randint(18, 70) + (random.randint(40, 160)
                                           if failover_reason else 0)

    request_id = "req_" + uuid.uuid4().hex[:18]
    auth_request = {
        "request_id": request_id,
        "account_id": account["account_id"],
        "instrument_token": instrument["instrument_token"],
        "merchant_id": merchant["merchant_id"],
        "region": region,
        "routing_region": routing_region,
        "payment_type": payment_type,
        "amount": amount,
        "currency": currency,
        "payload": _build_payload(payment_type, amount, currency),
        "created_at": ts,
    }

    decision = {
        "decision_id": "dec_" + uuid.uuid4().hex[:18],
        "request_id": request_id,
        "account_id": account["account_id"],
        # Denormalized display fields keep the live feed a single-collection read.
        "merchant_name": merchant["name"],
        "merchant_category": merchant["merchant_category"],
        "instrument_token": instrument["instrument_token"],
        "masked_number": instrument.get("masked_number"),
        "region": region,
        "routing_region": routing_region,
        "failover_reason": failover_reason,
        "payment_type": payment_type,
        "amount": amount,
        "currency": currency,
        "auth_status": status,
        "decline_reason": reason,
        "risk_flags": risk_flags,
        "latency_ms": latency_ms,
        "decided_at": ts,
        "created_at": ts,
        "updated_at": ts,
    }

    db.auth_requests.insert_one(dict(auth_request))
    db.auth_decisions.insert_one(dict(decision))
    _apply_ledger(db, account, request_id, amount, currency, status, ts)
    return decision


def _apply_ledger(db: Database, account: dict, request_id: str, amount: float,
                  currency: str, status: str, ts: datetime) -> None:
    """Record ledger movement and update the account's balance / hold state."""
    account_id = account["account_id"]
    if status == "approved":
        # Approved settles immediately in this simplified model.
        db.ledger_events.insert_one({
            "event_id": "led_" + uuid.uuid4().hex[:18],
            "account_id": account_id, "request_id": request_id,
            "type": "settlement", "amount": amount, "currency": currency,
            "created_at": ts,
        })
        db.accounts.update_one(
            {"account_id": account_id},
            {"$inc": {"available_balance": -amount},
             "$set": {"updated_at": ts}},
        )
    elif status == "pending":
        # Pending places a hold that reserves funds without settling.
        db.ledger_events.insert_one({
            "event_id": "led_" + uuid.uuid4().hex[:18],
            "account_id": account_id, "request_id": request_id,
            "type": "hold", "amount": amount, "currency": currency,
            "created_at": ts,
        })
        db.accounts.update_one(
            {"account_id": account_id},
            {"$inc": {"hold_amount": amount, "available_balance": -amount},
             "$set": {"updated_at": ts}},
        )
    # Declined authorizations move no money.


def _random_account(db: Database) -> dict:
    return next(iter(db.accounts.aggregate([{"$sample": {"size": 1}}])))


def _random_instrument(db: Database, account_id: str) -> dict:
    doc = next(iter(db.payment_instruments.aggregate(
        [{"$match": {"account_id": account_id}}, {"$sample": {"size": 1}}])), None)
    # Every seeded account has at least one instrument; guard just in case.
    return doc or {"instrument_token": "tok_unknown", "payment_type": "card_present",
                   "masked_number": "**** **** **** 0000"}


def _random_merchant(db: Database) -> dict:
    return next(iter(db.merchants.aggregate([{"$sample": {"size": 1}}])))


def take_snapshot(db: Database) -> int:
    """Persist a balance snapshot per account — a point-in-time balance view."""
    ts = _now()
    snaps = [{
        "account_id": a["account_id"],
        "available_balance": a.get("available_balance", 0.0),
        "hold_amount": a.get("hold_amount", 0.0),
        "currency": a.get("currency", "USD"),
        "snapshot_at": ts,
    } for a in db.accounts.find({}, {"account_id": 1, "available_balance": 1,
                                     "hold_amount": 1, "currency": 1})]
    if snaps:
        db.balance_snapshots.insert_many(snaps)
    return len(snaps)
