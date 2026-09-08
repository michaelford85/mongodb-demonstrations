"""The multi-document transaction demonstration.

Business operation: move an amount between two dedicated synthetic accounts and
write the corresponding transaction record. The invariant — money leaving one
account must arrive in the other, and the ledger entry must match — spans three
documents, which is exactly when a multi-document transaction earns its keep.

Isolated: only the two `purpose: transaction_demo` accounts are touched, and
every write the demo makes carries `demo_transfer: true` so reset can undo it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pymongo.errors import OperationFailure, PyMongoError

from lib.mongo_client import ACCOUNTS, DB_NAME, TRANSACTIONS, get_client, get_db
from lib.sample_data import (DEMO_TRANSFER_FLAG, TRANSFER_SOURCE,
                             TRANSFER_TARGET)

DEMO_ACCOUNTS = [TRANSFER_SOURCE, TRANSFER_TARGET]


class InsufficientFunds(RuntimeError):
    """Raised inside the transaction when the balance invariant would break."""


def balances() -> list:
    """Current balances of the two demo accounts, in a stable order."""
    docs = list(get_db()[ACCOUNTS].find(
        {"account_number": {"$in": DEMO_ACCOUNTS}},
        {"_id": 0, "account_number": 1, "account_type": 1, "balance": 1}))
    order = {acct: i for i, acct in enumerate(DEMO_ACCOUNTS)}
    return sorted(docs, key=lambda d: order.get(d["account_number"], 99))


def transaction_support() -> dict:
    """Report whether this deployment can run multi-document transactions."""
    try:
        hello = get_client().admin.command("hello")
    except PyMongoError as exc:
        return {"available": False,
                "reason": "Could not reach the deployment: {}".format(exc)}
    if hello.get("setName"):
        return {"available": True,
                "reason": "Connected to replica set '{}' — transactions are "
                          "supported.".format(hello["setName"])}
    if hello.get("msg") == "isdbgrid":
        return {"available": True,
                "reason": "Connected through a router — transactions are "
                          "supported."}
    return {"available": False,
            "reason": "This deployment does not report a replica set. "
                      "Multi-document transactions require a replica set or a "
                      "sharded deployment."}


def preview_transfer(amount: float, reverse: bool = False) -> dict:
    """Describe the intended operations without writing anything."""
    src, dst = (TRANSFER_TARGET, TRANSFER_SOURCE) if reverse else \
        (TRANSFER_SOURCE, TRANSFER_TARGET)
    return {
        "source": src,
        "target": dst,
        "amount": round(float(amount), 2),
        "operations": [
            {"step": 1, "collection": ACCOUNTS,
             "operation": "updateOne",
             "detail": "{{ account_number: '{}', balance: {{ $gte: {} }} }} "
                       "→ {{ $inc: {{ balance: -{} }} }}"
                       .format(src, round(amount, 2), round(amount, 2))},
            {"step": 2, "collection": ACCOUNTS,
             "operation": "updateOne",
             "detail": "{{ account_number: '{}' }} → "
                       "{{ $inc: {{ balance: +{} }} }}"
                       .format(dst, round(amount, 2))},
            {"step": 3, "collection": TRANSACTIONS,
             "operation": "insertOne",
             "detail": "one ledger entry, category 'transfer', "
                       "flagged {}: true".format(DEMO_TRANSFER_FLAG)},
        ],
        "invariant": "The debit only applies while the source balance covers "
                     "the amount. If it does not, the whole transaction aborts "
                     "and no document changes.",
    }


def _ledger_doc(src: str, dst: str, amount: float, now: datetime) -> dict:
    txn_id = "TXN-DEMO-{}".format(now.strftime("%Y%m%d%H%M%S%f"))
    return {
        "_id": txn_id,
        "txn_id": txn_id,
        "account_number": src,
        "counterparty_account": dst,
        "customer_id": "CUST-1001",
        "category": "transfer",
        "merchant": "Internal Transfer",
        "direction": "debit",
        "amount": round(float(amount), 2),
        "channel": "online",
        "posted_at": now,
        DEMO_TRANSFER_FLAG: True,
    }


def run_transfer(amount: float, reverse: bool = False) -> dict:
    """Execute the transfer in one session-based multi-document transaction."""
    plan = preview_transfer(amount, reverse)
    src, dst, amt = plan["source"], plan["target"], plan["amount"]
    before = balances()
    client = get_client()
    db = client[DB_NAME]
    now = datetime.now(timezone.utc)
    ledger = _ledger_doc(src, dst, amt, now)

    try:
        with client.start_session() as session:
            with session.start_transaction():
                debit = db[ACCOUNTS].update_one(
                    {"account_number": src, "balance": {"$gte": amt}},
                    {"$inc": {"balance": -amt}}, session=session)
                if debit.matched_count == 0:
                    raise InsufficientFunds(
                        "{} does not have {:.2f} available.".format(src, amt))
                db[ACCOUNTS].update_one({"account_number": dst},
                                        {"$inc": {"balance": amt}},
                                        session=session)
                db[TRANSACTIONS].insert_one(ledger, session=session)
    except InsufficientFunds as exc:
        return {"committed": False, "reason": str(exc), "kind": "invariant",
                "before": before, "after": balances(), "ledger": None}
    except OperationFailure as exc:
        return {"committed": False, "kind": "permission_or_capability",
                "reason": "The deployment rejected the transaction: {}"
                          .format(exc),
                "before": before, "after": balances(), "ledger": None}
    except PyMongoError as exc:
        return {"committed": False, "kind": "driver",
                "reason": "Transaction could not complete: {}".format(exc),
                "before": before, "after": balances(), "ledger": None}

    return {"committed": True, "kind": "ok", "reason": "Committed atomically.",
            "before": before, "after": balances(), "ledger": ledger}


def demo_transfer_history(limit: int = 10) -> list:
    """Ledger entries written by this demo, newest first."""
    return list(get_db()[TRANSACTIONS]
                .find({DEMO_TRANSFER_FLAG: True},
                      {"_id": 0, "txn_id": 1, "account_number": 1,
                       "counterparty_account": 1, "amount": 1, "posted_at": 1})
                .sort("posted_at", -1).limit(limit))
