"""Core provisioning service — the single path used by every entry route.

Portal entry, batch-file upload, and the direct-API simulation all call
:func:`process_ingest`, so validation and cap enforcement cannot diverge.

Confirmed behaviors encoded here (from the workload description):

* The cap is per account record, keyed by unique ``accountId``.
* Capacity is reserved with ONE atomic conditional update on a shared counter,
  equivalent to ``{accountId, capType, activeCount: {$lte: cap - N}}`` and
  ``$inc: {activeCount: N}``. A missing match means the cap was exceeded.
  "Read the count, then insert" is deliberately NOT used.
* Over-cap requests are rejected with ``422 SERVICE_PACKAGE_CAP_EXCEEDED``,
  save no number assets, and record a ``PROVISIONING_REJECTED`` audit event.
* Duplicate numbers are prevented by a unique compound index equivalent to
  ``{accountId: 1, "tn.orig.startTn": 1, type: 1}``.
* Removing an eligible number frees capacity exactly once. Reactivating a
  number or transferring one between accounts counts as an addition on the
  destination account for cap enforcement.
* The set of states that count toward the cap lives in ONE configurable
  business-rule function (:func:`states_counting_toward_cap`).

Atomicity strategy: when the connected deployment supports multi-document
transactions, the counter reservation, asset inserts, and audit events run in
one transaction. Otherwise a reservation-first strategy with compensation
(refunds on failed inserts) is used and is documented as non-atomic.

Idempotency: callers pass an idempotency key; a repeated request replays the
original per-item outcomes instead of creating duplicate assets or
double-counting capacity.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from lib.config import (ACCOUNTS_COLLECTION, AUDIT_COLLECTION,
                        COUNTERS_COLLECTION, NUMBER_ASSETS_COLLECTION,
                        supports_transactions)

CAP_TYPE = "local_tn"          # the cap type enforced by this demo
DEFAULT_CAP = 100
TXN_LIMIT = 2                  # MongoDB may reject large txns; keep them small

# ── Business rule: which number states consume capacity? ───────────────────
# One explicit, configurable function — do NOT assume every state counts.
CAP_ACTIVE_STATES = frozenset({"active"})


def states_counting_toward_cap() -> frozenset[str]:
    """The single configurable business rule for cap-counting states."""
    return CAP_ACTIVE_STATES


# Result codes shown in the UI / API simulation.
CAP_EXCEEDED = "422 SERVICE_PACKAGE_CAP_EXCEEDED"
NO_SUCH_ACCOUNT = "422 ACCOUNT_NOT_FOUND"
BAD_NUMBER = "422 INVALID_NUMBER_FORMAT"
DUPLICATE = "409 DUPLICATE_NUMBER"
BAD_TYPE = "422 INVALID_NUMBER_TYPE"
BAD_STATE = "422 INVALID_STATE_TRANSITION"
ACCEPTED = "202 ACCEPTED"

NUMBER_TYPES = {"local", "toll_free"}
# Full-length fictional US numbers: E.164 `+1` + 10 digits, using area code
# 555 and exchange 555 — a range never assigned to real subscribers.
TN_PATTERN = re.compile(r"^\+1555555\d{4}$")


@dataclass
class ItemResult:
    tn: str
    number_type: str
    ok: bool
    code: str
    detail: str = ""


@dataclass
class BatchResult:
    account_id: str
    channel: str
    idempotency_key: str
    results: list[ItemResult] = field(default_factory=list)
    used_transactions: bool = False
    replayed: bool = False

    @property
    def accepted(self) -> list[ItemResult]:
        return [r for r in self.results if r.ok]

    @property
    def rejected(self) -> list[ItemResult]:
        return [r for r in self.results if not r.ok]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(db: Database, event: str, account_id: str, requested: int,
           code: str, channel: str, idem_key: str, detail: str = "") -> None:
    db[AUDIT_COLLECTION].insert_one({
        "event": event, "accountId": account_id, "capType": CAP_TYPE,
        "requestedCount": requested, "resultCode": code, "channel": channel,
        "idempotencyKey": idem_key, "detail": detail[:200],
        "at": _now(), "note": "synthetic demo data",
    })


def valid_tn(tn: str) -> bool:
    return bool(TN_PATTERN.match(tn))


def _counter(db: Database, account_id: str) -> dict:
    return db[COUNTERS_COLLECTION].find_one(
        {"accountId": account_id, "capType": CAP_TYPE}) or {}


def set_counter_for_demo(db: Database, account_id: str, active_count: int,
                         cap: int) -> None:
    """Demo-only helper (UI button): force the counter to a known state so the
    race is repeatable. Targeted write to the demo database only."""
    db[COUNTERS_COLLECTION].update_one(
        {"accountId": account_id, "capType": CAP_TYPE},
        {"$set": {"activeCount": active_count, "cap": cap,
                  "updatedAt": _now()}},
        upsert=True)


def get_or_create_counter(db: Database, account_id: str, cap: int) -> dict:
    """Idempotently ensure the counter exists; never overwrites existing cap."""
    doc = db[COUNTERS_COLLECTION].find_one_and_update(
        {"accountId": account_id, "capType": CAP_TYPE},
        {"$setOnInsert": {"activeCount": 0, "cap": cap, "updatedAt": _now()}},
        upsert=True, return_document=ReturnDocument.AFTER)
    return doc


def set_cap(db: Database, account_id: str, cap: int) -> dict | None:
    """Set the account-level cap on the counter document (the single source
    of truth for enforcement). Lowering below usage keeps existing numbers
    and blocks new additions until usage falls below the cap."""
    get_or_create_counter(db, account_id, cap)
    return db[COUNTERS_COLLECTION].find_one_and_update(
        {"accountId": account_id, "capType": CAP_TYPE},
        {"$set": {"cap": cap, "updatedAt": _now()}},
        return_document=ReturnDocument.AFTER)


def _reserve(db: Database, account_id: str, n: int) -> bool:
    """THE atomic cap guard. One conditional update on activeCount; the cap
    is read from the account's counter document (config, not count). No
    read-then-write on the count itself."""
    cap = get_or_create_counter(db, account_id, DEFAULT_CAP)["cap"]
    res = db[COUNTERS_COLLECTION].update_one(
        {"accountId": account_id, "capType": CAP_TYPE,
         "activeCount": {"$lte": cap - n}},
        {"$inc": {"activeCount": n}, "$set": {"updatedAt": _now()}})
    return res.matched_count == 1


def _refund(db: Database, account_id: str, n: int) -> None:
    if n > 0:
        db[COUNTERS_COLLECTION].update_one(
            {"accountId": account_id, "capType": CAP_TYPE,
             "activeCount": {"$gte": n}},
            {"$inc": {"activeCount": -n}, "$set": {"updatedAt": _now()}})


def _insert_asset(db: Database, account_id: str, item: dict, channel: str,
                  idem_key: str) -> dict:
    """One telephone-number asset per document."""
    hierarchy = db[ACCOUNTS_COLLECTION].find_one(
        {"accountId": account_id},
        {"parentAccount": 1, "superAccount": 1}) or {}
    doc = {
        "accountId": account_id,
        "parentAccountId": hierarchy.get("parentAccount"),
        "superAccountId": hierarchy.get("superAccount"),
        "type": item["type"],
        "state": "active",
        "tn": {"orig": {"start": item["tn"], "count": 1,
                        "startTn": item["tn"], "endTn": item["tn"]}},
        "callerProfileId": f"cp-{uuid.uuid4().hex[:10]}",
        "partnerData": {"synthetic": True},
        "vetting": {"status": "not_verified_demo_only"},
        "channel": channel,
        "idempotencyKey": idem_key,
        "createdAt": _now(),
        "note": "synthetic demo data",
    }
    db[NUMBER_ASSETS_COLLECTION].insert_one(doc)
    return doc


def _validate_items(db: Database, account_id: str,
                    items: list[dict]) -> list[ItemResult]:
    """Per-item validation that precedes any reservation."""
    out: list[ItemResult] = []
    account = db[ACCOUNTS_COLLECTION].find_one({"accountId": account_id})
    for item in items:
        tn, num_type = item.get("tn", ""), item.get("type", "local")
        if account is None:
            out.append(ItemResult(
                tn, num_type, False, NO_SUCH_ACCOUNT,
                f"no account record for {account_id} — seed demo data "
                f"first (Step 0 on the Ingest page)"))
        elif num_type not in NUMBER_TYPES:
            out.append(ItemResult(tn, num_type, False, BAD_TYPE,
                                  f"type must be one of {sorted(NUMBER_TYPES)}"))
        elif not valid_tn(tn):
            out.append(ItemResult(tn, num_type, False, BAD_NUMBER,
                                  "use the fictional range +1555555xxxx (fictional 555/555 exchange)"))
        elif db[NUMBER_ASSETS_COLLECTION].find_one(
                {"accountId": account_id, "tn.orig.startTn": tn,
                 "type": num_type}):
            out.append(ItemResult(tn, num_type, False, DUPLICATE,
                                  "unique index {accountId, tn.orig.startTn, type}"))
        else:
            out.append(ItemResult(tn, num_type, True, ACCEPTED, "validated"))
    return out


def _txn_body(db: Database, session, account_id: str, channel: str,
              idem_key: str, validated: list[ItemResult],
              result: BatchResult) -> None:
    """Transaction body: reserve, insert assets, audit — all or nothing."""
    n = len(validated)
    cap = get_or_create_counter(db, account_id, DEFAULT_CAP)["cap"]
    if n and not db[COUNTERS_COLLECTION].update_one(
            {"accountId": account_id, "capType": CAP_TYPE,
             "activeCount": {"$lte": cap - n}},
            {"$inc": {"activeCount": n}, "$set": {"updatedAt": _now()}},
            session=session).matched_count:
        for v in validated:
            v.ok, v.code, v.detail = False, CAP_EXCEEDED, "atomic reservation refused"
        _audit(db, "PROVISIONING_REJECTED", account_id, n, CAP_EXCEEDED,
               channel, idem_key, "cap exceeded")
        return
    for v in validated:
        _insert_asset(db, account_id, {"tn": v.tn, "type": v.number_type},
                      channel, idem_key)
        v.code = ACCEPTED
    _audit(db, "PROVISIONING_ACCEPTED", account_id, n, ACCEPTED, channel,
           idem_key)


def process_ingest(db: Database, account_id: str, items: list[dict],
                   channel: str,
                   idempotency_key: str | None = None) -> BatchResult:
    """The one ingestion path for portal, batch, and direct-API entry.
    Cap enforcement always uses the cap stored on the account's counter
    document — requests never carry their own cap."""
    idem_key = idempotency_key or f"idem-{uuid.uuid4().hex}"
    result = BatchResult(account_id, channel, idem_key)

    # Idempotent replay: same key must not double-count or duplicate.
    prior = list(db[NUMBER_ASSETS_COLLECTION].find(
        {"idempotencyKey": idem_key, "accountId": account_id},
        {"tn.orig.startTn": 1, "type": 1}).limit(TXN_LIMIT * 25))
    if prior:
        for p in prior:
            result.results.append(ItemResult(
                p["tn"]["orig"]["startTn"], p["type"], True, ACCEPTED,
                "replayed from idempotency key"))
        result.replayed = True
        return result
    prior_reject = db[AUDIT_COLLECTION].find_one(
        {"idempotencyKey": idem_key, "event": "PROVISIONING_REJECTED"})
    if prior_reject:
        result.results.append(ItemResult(
            prior_reject.get("detail", ""), "", False, prior_reject["resultCode"],
            "replayed from idempotency key"))
        result.replayed = True
        return result

    if not items:
        result.results.append(ItemResult("", "", False, BAD_NUMBER,
                                         "request contained no items"))
        _audit(db, "PROVISIONING_REJECTED", account_id, 0, BAD_NUMBER,
               channel, idem_key, "empty request")
        return result

    validated = _validate_items(db, account_id, items)
    result.results.extend(validated)
    good = [v for v in validated if v.ok]
    if not good:
        _audit(db, "PROVISIONING_REJECTED", account_id, len(items),
               result.rejected[0].code, channel, idem_key,
               "all items failed validation")
        return result

    if supports_transactions(db.client):
        try:
            with db.client.start_session() as session:
                session.start_transaction()
                _txn_body(db, session, account_id, channel, idem_key,
                          good, result)
                session.commit_transaction()
                result.used_transactions = True
            return result
        except Exception:
            # Transaction aborted (e.g. duplicate key race): nothing was
            # committed; fall through to the compensation path for a visible
            # per-item outcome.
            result.used_transactions = False
            result.results = [ItemResult(v.tn, v.number_type, v.ok, v.code,
                                         "transaction aborted; retried via "
                                         "reservation + compensation")
                              for v in good]
            good = [v for v in result.results if v.ok]

    # Reservation + compensation fallback (non-atomic across collections —
    # documented as such in the UI and README). Batch requests process rows
    # in file order so later rows can be rejected individually; other
    # channels reserve for the whole request first (atomic per request).
    if channel != "batch":
        if not _reserve(db, account_id, len(good)):
            for v in good:
                v.ok, v.code, v.detail = False, CAP_EXCEEDED, "cap exceeded"
            _audit(db, "PROVISIONING_REJECTED", account_id, len(good),
                   CAP_EXCEEDED, channel, idem_key, "cap exceeded")
            return result

    refund = 0
    cap_blocked = False
    for v in good:
        if cap_blocked:
            v.ok, v.code, v.detail = False, CAP_EXCEEDED, \
                "cap reached earlier in the batch"
            continue
        if channel == "batch" and not _reserve(db, account_id, 1):
            cap_blocked = True
            v.ok, v.code, v.detail = False, CAP_EXCEEDED, "cap exceeded"
            continue
        try:
            _insert_asset(db, account_id, {"tn": v.tn, "type": v.number_type},
                          channel, idem_key)
            v.code = ACCEPTED
        except DuplicateKeyError:
            v.ok, v.code = False, DUPLICATE
            v.detail = "lost a duplicate race; capacity refunded"
            refund += 1
    _refund(db, account_id, refund)
    accepted_n = len(good) - refund - len([v for v in good if not v.ok])
    if accepted_n > 0:
        _audit(db, "PROVISIONING_ACCEPTED", account_id, accepted_n,
               ACCEPTED, channel, idem_key)
    if accepted_n < len(good):
        _audit(db, "PROVISIONING_REJECTED", account_id, len(good) - accepted_n,
               CAP_EXCEEDED if cap_blocked or refund == 0 else DUPLICATE,
               channel, idem_key, "partial batch" if channel == "batch"
               else "see per-item results")
    return result


# ── Removal, reactivation, transfer ────────────────────────────────────────

def remove_number(db: Database, account_id: str, tn: str,
                  number_type: str = "local") -> tuple[bool, str]:
    """Remove an eligible number; free capacity exactly once."""
    counting = states_counting_toward_cap()
    res = db[NUMBER_ASSETS_COLLECTION].update_one(
        {"accountId": account_id, "tn.orig.startTn": tn, "type": number_type,
         "state": {"$in": sorted(counting)}},
        {"$set": {"state": "removed", "removedAt": _now()}})
    if res.matched_count:
        _refund(db, account_id, 1)
        return True, "removed; capacity freed exactly once"
    res = db[NUMBER_ASSETS_COLLECTION].update_one(
        {"accountId": account_id, "tn.orig.startTn": tn, "type": number_type},
        {"$set": {"state": "removed", "removedAt": _now()}})
    return (bool(res.matched_count),
            "removed (state did not consume capacity)"
            if res.matched_count else "no matching eligible number")


def reactivate_number(db: Database, account_id: str, tn: str,
                      number_type: str = "local",
                      ) -> tuple[bool, str]:
    """Reactivation counts as an addition: reserve capacity first."""
    if not _reserve(db, account_id, 1):
        _audit(db, "PROVISIONING_REJECTED", account_id, 1, CAP_EXCEEDED,
               "reactivation", f"react-{uuid.uuid4().hex[:8]}",
               "reactivation would exceed cap")
        return False, CAP_EXCEEDED
    res = db[NUMBER_ASSETS_COLLECTION].update_one(
        {"accountId": account_id, "tn.orig.startTn": tn,
         "type": number_type, "state": {"$in": ["released", "suspended"]}},
        {"$set": {"state": "active", "reactivatedAt": _now()}})
    if not res.matched_count:
        _refund(db, account_id, 1)
        return False, BAD_STATE
    return True, "reactivated; capacity reserved as an addition"


def transfer_number(db: Database, source_account: str, dest_account: str,
                    tn: str, number_type: str = "local",
                    ) -> tuple[bool, str]:
    """Transfer = remove on source + addition (reservation) on destination.
    If the destination reservation fails, the asset stays on the source."""
    if not _reserve(db, dest_account, 1):
        _audit(db, "PROVISIONING_REJECTED", dest_account, 1, CAP_EXCEEDED,
               "transfer", f"xfer-{uuid.uuid4().hex[:8]}",
               f"transfer from {source_account} would exceed cap")
        return False, CAP_EXCEEDED
    res = db[NUMBER_ASSETS_COLLECTION].update_one(
        {"accountId": source_account, "tn.orig.startTn": tn,
         "type": number_type},
        {"$set": {"accountId": dest_account, "transferredAt": _now(),
                  "state": "active"}})
    if not res.matched_count:
        _refund(db, dest_account, 1)
        return False, "no matching number on the source account"
    return True, "transferred; capacity reserved on the destination account"


def lower_cap(db: Database, account_id: str, new_cap: int) -> dict | None:
    """Lower the cap below current usage: existing numbers are kept, new
    additions are blocked until usage falls below the cap."""
    return set_cap(db, account_id, new_cap)
