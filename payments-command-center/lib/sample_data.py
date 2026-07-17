"""Synthetic data builders for Northstar Payments.

Everything here is fictional. Card numbers are masked, tokens are random, and
no real cardholder data is ever produced. Deterministic seeding keeps demos and
screenshots reproducible across machines.
"""

import random
import uuid
from datetime import datetime, timedelta, timezone

from lib.atlas_client import PAYMENT_TYPES, REGIONS

random.seed(42)

CARD_NETWORKS = ["Visa", "Mastercard", "Amex", "Discover"]
WALLET_PROVIDERS = ["NorthPay Wallet", "Meridian Pay", "OrbitPay"]
# Currency per real demo region (us-east / us-west / eu).
CURRENCIES = {"us-east": "USD", "us-west": "USD", "eu": "EUR"}

MERCHANT_CATALOG = [
    ("Aurora Coffee Roasters", "food_and_beverage"),
    ("Summit Outfitters", "retail"),
    ("Nimbus Cloud Storage", "digital_goods"),
    ("Harbor Grocery Co", "grocery"),
    ("Vertex Airlines", "travel"),
    ("Lumen Streaming", "subscription"),
    ("Ironwood Furniture", "home"),
    ("Pulse Fitness", "health"),
    ("Cobalt Electronics", "electronics"),
    ("Willow Pharmacy", "pharmacy"),
]

RISK_FLAGS = [
    "velocity_high", "geo_mismatch", "new_device", "amount_outlier",
    "merchant_watchlist", "token_reuse",
]

FIRST_NAMES = ["Ava", "Liam", "Noah", "Mia", "Elena", "Marcus", "Priya",
               "Diego", "Sofia", "Kenji", "Amara", "Lucas"]
LAST_NAMES = ["Reyes", "Okafor", "Nguyen", "Silva", "Novak", "Haddad",
              "Lindqvist", "Costa", "Ibrahim", "Tanaka", "Moreau", "Park"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_token() -> str:
    return "tok_" + uuid.uuid4().hex[:20]


def masked_card() -> str:
    return "**** **** **** " + f"{random.randint(0, 9999):04d}"


def build_accounts(n: int = 40) -> list[dict]:
    accounts = []
    for i in range(1, n + 1):
        region = random.choice(REGIONS)
        limit = random.choice([1500, 3000, 5000, 10000, 25000])
        available = round(limit * random.uniform(0.2, 0.95), 2)
        accounts.append({
            "account_id": f"ACC-{100000 + i}",
            "holder_name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
            "region": region,
            "currency": CURRENCIES[region],
            "tier": random.choices(["standard", "gold", "platinum"],
                                   weights=[65, 25, 10])[0],
            "credit_limit": limit,
            "available_balance": available,
            "hold_amount": 0.0,
            "created_at": _now() - timedelta(days=random.randint(30, 900)),
            "updated_at": _now(),
        })
    return accounts


def build_instruments(accounts: list[dict]) -> list[dict]:
    """Each account gets 1-3 instruments spanning the payment-type shapes."""
    instruments = []
    for acct in accounts:
        for _ in range(random.randint(1, 3)):
            ptype = random.choice(PAYMENT_TYPES)
            base = {
                "instrument_token": new_token(),
                "account_id": acct["account_id"],
                # Co-located with the owning account for zone sharding.
                "region": acct["region"],
                "payment_type": ptype,
                "masked_number": masked_card(),
                "created_at": _now() - timedelta(days=random.randint(1, 400)),
            }
            # Flexible model: each shape carries only the fields that apply.
            if ptype == "card_present":
                base |= {"network": random.choice(CARD_NETWORKS),
                         "entry_capable": ["chip", "contactless", "swipe"]}
            elif ptype == "wallet_token":
                base |= {"network": random.choice(CARD_NETWORKS),
                         "wallet_provider": random.choice(WALLET_PROVIDERS),
                         "device_bound": True}
            else:  # installment
                base |= {"plan_provider": random.choice(WALLET_PROVIDERS),
                         "max_plan_months": random.choice([3, 6, 12])}
            instruments.append(base)
    return instruments


def build_merchants() -> list[dict]:
    merchants = []
    for i, (name, category) in enumerate(MERCHANT_CATALOG, 1):
        merchants.append({
            "merchant_id": f"MER-{2000 + i}",
            "name": name,
            "merchant_category": category,
            "region": random.choice(REGIONS),
            "mcc": f"{random.randint(4000, 7999)}",
        })
    return merchants
