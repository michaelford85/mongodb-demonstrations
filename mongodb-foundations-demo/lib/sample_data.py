"""Deterministic synthetic dataset for the MongoDB Foundations walkthrough.

Every name, city, account number, and amount is invented for this demo. There is
no real customer, no PII, and no production-like credential anywhere in here.

The generators are seeded, so a reset always rebuilds byte-identical documents.
That keeps the presenter's screen, talk track, and index behaviour reproducible.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

SEED = 20250101
BASE_DATE = datetime(2025, 1, 6, tzinfo=timezone.utc)

CONTACT_CHANNELS = ["email", "sms", "paper_mail"]
LANGUAGES = ["en", "es"]
ACCOUNT_TYPES = ["checking", "savings", "credit_card", "auto_loan"]
CATEGORIES = ["groceries", "utilities", "travel", "dining", "fuel",
              "subscription", "transfer"]
ALERT_TYPES = ["address_change", "new_account", "score_change", "dispute_filed"]
MERCHANTS = ["Northwind Grocers", "Cedar Utilities Co-op", "Halcyon Air",
             "The Copper Skillet", "Larkspur Fuel", "Brightline Media",
             "Internal Transfer"]

# Invented city / state pairs. Real state codes keep the geography filter
# readable; the city names are fictional.
PLACES = [("Cedar Hollow", "IL"), ("Marlow Bend", "TX"),
          ("Prairie Junction", "GA"), ("Northgate Springs", "CA"),
          ("Silver Fork", "OH"), ("Elmsford Park", "AZ")]

FIRST_NAMES = ["Ada", "Bo", "Cyra", "Devin", "Elsie", "Ferris", "Gwen",
               "Hollis", "Imani", "Jonas", "Kira", "Lorne"]
LAST_NAMES = ["Aldridge", "Beckworth", "Calloway", "Danforth", "Ellery",
              "Fairhaven", "Grimsby", "Holloway", "Ingersoll", "Jarrow",
              "Kestrel", "Lindqvist"]

CUSTOMER_COUNT = 12
TRANSACTION_COUNT = 240

# The two dedicated accounts the transaction demo moves money between. They are
# never touched by the seeded transaction history, so the demo stays isolated.
TRANSFER_SOURCE = "ACCT-90001"
TRANSFER_TARGET = "ACCT-90002"
TRANSFER_SOURCE_OPENING = 4200.00
TRANSFER_TARGET_OPENING = 1500.00
TRANSFER_CUSTOMER = "CUST-1001"

# Marker on every document written by the transaction demo, so reset can remove
# exactly those and nothing else.
DEMO_TRANSFER_FLAG = "demo_transfer"


def customer_id(i: int) -> str:
    return "CUST-{:04d}".format(1000 + i)


def build_customers() -> list:
    """Twelve customer profiles: nested address/contact/preferences + alerts."""
    rnd = random.Random(SEED)
    docs = []
    for i in range(1, CUSTOMER_COUNT + 1):
        city, state = PLACES[(i - 1) % len(PLACES)]
        cid = customer_id(i)
        first, last = FIRST_NAMES[i - 1], LAST_NAMES[i - 1]
        alerts = [
            {
                "alert_id": "ALRT-{}-{}".format(cid[-4:], n + 1),
                "type": ALERT_TYPES[(i + n) % len(ALERT_TYPES)],
                "opened_at": BASE_DATE - timedelta(days=rnd.randint(5, 200)),
                "channel": CONTACT_CHANNELS[(i + n) % len(CONTACT_CHANNELS)],
            }
            for n in range(rnd.randint(1, 3))  # bounded array: at most 3
        ]
        docs.append({
            "_id": cid,
            "customer_id": cid,
            "name": {"first": first, "last": last},
            "segment": "small_business" if i % 4 == 0 else "consumer",
            "joined_on": BASE_DATE - timedelta(days=300 + i * 17),
            "address": {
                "street": "{} {} Street".format(100 + i * 7, last),
                "city": city,
                "state": state,
                "postal_code": "{:05d}".format(60000 + i * 111),
                "country": "US",
            },
            "contact": {
                "email": "{}.{}@example.invalid".format(first.lower(),
                                                       last.lower()),
                "phone": "+1-555-01{:02d}".format(i),
            },
            "preferences": {
                "contact_channel": CONTACT_CHANNELS[i % len(CONTACT_CHANNELS)],
                "paperless": i % 3 != 0,
                "language": LANGUAGES[i % len(LANGUAGES)],
                "alerts_enabled": i % 5 != 0,
            },
            # Bounded, read-together history. Capped by design, not unbounded.
            "recent_alerts": alerts,
        })
    return docs


def build_accounts() -> list:
    """One or two accounts per customer, plus the two transfer-demo accounts."""
    rnd = random.Random(SEED + 1)
    docs = []
    number = 50000
    for i in range(1, CUSTOMER_COUNT + 1):
        cid = customer_id(i)
        for n in range(1 if i % 3 == 0 else 2):
            number += 1
            acct_type = ACCOUNT_TYPES[(i + n) % len(ACCOUNT_TYPES)]
            docs.append({
                "_id": "ACCT-{}".format(number),
                "account_number": "ACCT-{}".format(number),
                "customer_id": cid,
                "account_type": acct_type,
                "status": "closed" if (i == CUSTOMER_COUNT and n == 1) else "open",
                "opened_on": BASE_DATE - timedelta(days=200 + i * 11 + n * 40),
                "currency": "USD",
                "balance": round(rnd.uniform(250, 9500), 2),
            })
    for acct, opening, label in (
        (TRANSFER_SOURCE, TRANSFER_SOURCE_OPENING, "checking"),
        (TRANSFER_TARGET, TRANSFER_TARGET_OPENING, "savings"),
    ):
        docs.append({
            "_id": acct,
            "account_number": acct,
            "customer_id": TRANSFER_CUSTOMER,
            "account_type": label,
            "status": "open",
            "opened_on": BASE_DATE - timedelta(days=365),
            "currency": "USD",
            "balance": opening,
            "purpose": "transaction_demo",
        })
    return docs


def build_transactions(account_docs: list) -> list:
    """A modest, deterministic transaction history for filtering + aggregation.

    The two transaction-demo accounts are excluded so their balances only ever
    change through the demonstrated multi-document transaction.
    """
    rnd = random.Random(SEED + 2)
    postable = [a for a in account_docs
                if a.get("purpose") != "transaction_demo"
                and a["status"] == "open"]
    docs = []
    for n in range(1, TRANSACTION_COUNT + 1):
        acct = postable[n % len(postable)]
        cat_idx = n % len(CATEGORIES)
        docs.append({
            "_id": "TXN-{:06d}".format(n),
            "txn_id": "TXN-{:06d}".format(n),
            "account_number": acct["account_number"],
            "customer_id": acct["customer_id"],
            "category": CATEGORIES[cat_idx],
            "merchant": MERCHANTS[cat_idx],
            "direction": "credit" if n % 9 == 0 else "debit",
            "amount": round(rnd.uniform(4.50, 890.00), 2),
            "channel": "card" if n % 2 else "ach",
            "posted_at": BASE_DATE - timedelta(days=n % 180,
                                               hours=(n * 7) % 24),
        })
    return docs


def build_all() -> tuple:
    """Return (customers, accounts, transactions) for a full seed."""
    customer_docs = build_customers()
    account_docs = build_accounts()
    return customer_docs, account_docs, build_transactions(account_docs)
