"""Read-side query helpers for the dashboard, explorer, and account views.

Each function returns plain Python structures so the Streamlit layer stays thin
and every aggregation pipeline is easy to read out loud during a live demo.
"""

from datetime import datetime, timedelta, timezone

from pymongo.database import Database


def _cutoff(minutes: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


def recent_feed(db: Database, limit: int = 40) -> list[dict]:
    """Latest authorization decisions — the live feed, one collection read."""
    return list(db.auth_decisions.find().sort("decided_at", -1).limit(limit))


def dashboard_metrics(db: Database, window_minutes: int = 10) -> dict:
    """Headline numbers: approval rate, throughput, latency, regional split."""
    since = _cutoff(window_minutes)
    pipeline = [
        {"$match": {"decided_at": {"$gte": since}}},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "approved": {"$sum": {"$cond": [{"$eq": ["$auth_status", "approved"]}, 1, 0]}},
            "declined": {"$sum": {"$cond": [{"$eq": ["$auth_status", "declined"]}, 1, 0]}},
            "pending": {"$sum": {"$cond": [{"$eq": ["$auth_status", "pending"]}, 1, 0]}},
            "avg_latency": {"$avg": "$latency_ms"},
            "rerouted": {"$sum": {"$cond": [{"$ne": ["$failover_reason", None]}, 1, 0]}},
        }},
    ]
    agg = next(iter(db.auth_decisions.aggregate(pipeline)), None)
    total = agg["total"] if agg else 0
    approved = agg["approved"] if agg else 0
    return {
        "window_minutes": window_minutes,
        "total": total,
        "approved": approved,
        "declined": agg["declined"] if agg else 0,
        "pending": agg["pending"] if agg else 0,
        "rerouted": agg["rerouted"] if agg else 0,
        "approval_rate": (approved / total * 100) if total else 0.0,
        "tpm": total / window_minutes if window_minutes else 0.0,
        "avg_latency_ms": round(agg["avg_latency"], 1) if agg and agg["avg_latency"] else 0.0,
    }


def regional_breakdown(db: Database, window_minutes: int = 10) -> list[dict]:
    """Volume and approval rate grouped by region, for the regional panel."""
    since = _cutoff(window_minutes)
    pipeline = [
        {"$match": {"decided_at": {"$gte": since}}},
        {"$group": {
            "_id": "$region",
            "volume": {"$sum": 1},
            "approved": {"$sum": {"$cond": [{"$eq": ["$auth_status", "approved"]}, 1, 0]}},
            "avg_latency": {"$avg": "$latency_ms"},
        }},
        {"$sort": {"volume": -1}},
    ]
    out = []
    for row in db.auth_decisions.aggregate(pipeline):
        vol = row["volume"]
        out.append({
            "region": row["_id"],
            "volume": vol,
            "approval_rate": round(row["approved"] / vol * 100, 1) if vol else 0.0,
            "avg_latency_ms": round(row["avg_latency"], 1) if row["avg_latency"] else 0.0,
        })
    return out


def payment_type_mix(db: Database, window_minutes: int = 60) -> list[dict]:
    """Counts per payment-event shape — powers the schema-evolution story."""
    since = _cutoff(window_minutes)
    pipeline = [
        {"$match": {"decided_at": {"$gte": since}}},
        {"$group": {"_id": "$payment_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    return [{"payment_type": r["_id"], "count": r["count"]}
            for r in db.auth_decisions.aggregate(pipeline)]


def risk_flag_counts(db: Database, window_minutes: int = 60) -> list[dict]:
    """Frequency of each risk flag — feeds the risk panel."""
    since = _cutoff(window_minutes)
    pipeline = [
        {"$match": {"decided_at": {"$gte": since}, "risk_flags.0": {"$exists": True}}},
        {"$unwind": "$risk_flags"},
        {"$group": {"_id": "$risk_flags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    return [{"flag": r["_id"], "count": r["count"]}
            for r in db.auth_decisions.aggregate(pipeline)]


def search_transactions(db: Database, *, merchant: str = "", region: str = "",
                        status: str = "", payment_type: str = "",
                        token: str = "", limit: int = 100) -> list[dict]:
    """Filtered transaction search for the explorer."""
    query: dict = {}
    if merchant:
        query["merchant_name"] = {"$regex": merchant, "$options": "i"}
    if region:
        query["region"] = region
    if status:
        query["auth_status"] = status
    if payment_type:
        query["payment_type"] = payment_type
    if token:
        query["instrument_token"] = {"$regex": token, "$options": "i"}
    return list(db.auth_decisions.find(query).sort("decided_at", -1).limit(limit))


def transaction_detail(db: Database, request_id: str) -> dict:
    """Join a decision to its originating request for the detail view."""
    decision = db.auth_decisions.find_one({"request_id": request_id})
    request = db.auth_requests.find_one({"request_id": request_id})
    ledger = list(db.ledger_events.find({"request_id": request_id}))
    return {"decision": decision, "request": request, "ledger": ledger}


def list_accounts(db: Database, limit: int = 200) -> list[dict]:
    return list(db.accounts.find().sort("account_id", 1).limit(limit))


def account_overview(db: Database, account_id: str) -> dict:
    """Balance, holds, recent authorizations, and recent settlements."""
    account = db.accounts.find_one({"account_id": account_id})
    recent_auths = list(db.auth_decisions.find({"account_id": account_id})
                        .sort("decided_at", -1).limit(10))
    settlements = list(db.ledger_events.find(
        {"account_id": account_id, "type": "settlement"})
        .sort("created_at", -1).limit(10))
    holds = list(db.ledger_events.find(
        {"account_id": account_id, "type": "hold"})
        .sort("created_at", -1).limit(10))
    return {"account": account, "recent_auths": recent_auths,
            "settlements": settlements, "holds": holds}
