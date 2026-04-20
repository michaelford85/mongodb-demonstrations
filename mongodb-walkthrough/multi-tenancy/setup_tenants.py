"""
Splits sample_mflix.movies across three tenant databases by release era and
creates a scoped Atlas database user for each tenant.

Tenant databases created:
  classicflix        — year < 1980  (malformed string years also land here)
  millenniumstream   — 1980 <= year < 2000
  modernplex         — year >= 2000

Each tenant gets:
  · movies   collection — their slice of sample_mflix.movies
  · config   collection — one document describing the tenant

Each tenant also gets a dedicated Atlas database user (read-only) scoped
exclusively to that tenant's database.  Attempting to use those credentials
against any other database returns an authorization error at the Atlas level —
enforcement is not dependent on application logic.

Run once. Re-running detects existing tenant databases and exits cleanly.
"""

import os
import re
import sys
import requests
from pymongo import MongoClient
from pymongo.errors import BulkWriteError
from requests.auth import HTTPDigestAuth
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI  = os.environ["MONGODB_URI"]
PUBLIC_KEY   = os.environ.get("ATLAS_PUBLIC_KEY", "")
PRIVATE_KEY  = os.environ.get("ATLAS_PRIVATE_KEY", "")
PROJECT_ID   = os.environ.get("ATLAS_PROJECT_ID", "")

SOURCE_DB   = "sample_mflix"
SOURCE_COLL = "movies"
BATCH_SIZE  = 500

BASE_URL = "https://cloud.mongodb.com/api/atlas/v2"
AUTH     = HTTPDigestAuth(PUBLIC_KEY, PRIVATE_KEY) if PUBLIC_KEY else None
HEADERS  = {
    "Content-Type": "application/json",
    "Accept": "application/vnd.atlas.2023-01-01+json",
}

TENANTS = {
    "classicflix": {
        "display_name": "ClassicFlix",
        "description":  "Classic cinema — pre-1980",
        "year_range":   "year < 1980",
        "password_env": "CLASSICFLIX_PASSWORD",
    },
    "millenniumstream": {
        "display_name": "MillenniumStream",
        "description":  "The golden age of modern cinema — 1980 to 1999",
        "year_range":   "1980 – 1999",
        "password_env": "MILLENNIUMSTREAM_PASSWORD",
    },
    "modernplex": {
        "display_name": "ModernPlex",
        "description":  "Contemporary cinema — 2000 and beyond",
        "year_range":   "year >= 2000",
        "password_env": "MODERNPLEX_PASSWORD",
    },
}


def parse_year(val):
    """
    Return an integer year from an int or a malformed string (e.g. '1981è',
    '1994è1998').  Extracts the first four-digit sequence it finds.
    Returns None if unparseable.
    """
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        m = re.match(r'(\d{4})', val.strip())
        if m:
            return int(m.group(1))
    return None


def classify(doc):
    """Return the tenant name for a given movie document."""
    year = parse_year(doc.get("year"))
    if year is None or year < 1980:
        return "classicflix"
    elif year < 2000:
        return "millenniumstream"
    else:
        return "modernplex"


def insert_batched(collection, docs):
    """Insert docs in batches, tolerating duplicate-key errors."""
    inserted = 0
    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i : i + BATCH_SIZE]
        try:
            result = collection.insert_many(batch, ordered=False)
            inserted += len(result.inserted_ids)
        except BulkWriteError as e:
            inserted += e.details.get("nInserted", 0)
    return inserted


def create_atlas_user(username, password, db_name):
    """Create a read-only Atlas database user scoped to db_name."""
    if not AUTH:
        return "skipped"
    url  = f"{BASE_URL}/groups/{PROJECT_ID}/databaseUsers"
    body = {
        "databaseName": "admin",
        "username":     username,
        "password":     password,
        "roles": [{"databaseName": db_name, "roleName": "read"}],
    }
    resp = requests.post(url, auth=AUTH, headers=HEADERS, json=body)
    if resp.status_code == 409:
        return "already exists"
    if not resp.ok:
        raise RuntimeError(f"Atlas API error {resp.status_code}: {resp.text}")
    return "created"


def main():
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)

    # ── Guard: already set up? ──────────────────────────────────────
    existing = [t for t in TENANTS if t in client.list_database_names()]
    if existing:
        print("Tenant databases already exist — nothing to do.")
        for name in existing:
            count = client[name].movies.estimated_document_count()
            print(f"  {name:<22}  {count:>7,} movies")
        print("\nRun teardown_tenants.py first if you want to recreate them.")
        client.close()
        return

    # ── Guard: source data present? ────────────────────────────────
    source_count = client[SOURCE_DB][SOURCE_COLL].estimated_document_count()
    if source_count == 0:
        print(f"ERROR: {SOURCE_DB}.{SOURCE_COLL} is empty.")
        print("Load the Atlas sample dataset first:")
        print("  Atlas UI → your cluster → … → Load Sample Dataset")
        client.close()
        sys.exit(1)

    print(f"Classifying {source_count:,} movies from {SOURCE_DB}.{SOURCE_COLL}...\n")

    # ── Classify all movies ─────────────────────────────────────────
    buckets = {name: [] for name in TENANTS}
    for doc in client[SOURCE_DB][SOURCE_COLL].find({}):
        buckets[classify(doc)].append(doc)

    for name, docs in buckets.items():
        print(f"  {name:<22}  {len(docs):>7,} movies  ({TENANTS[name]['year_range']})")

    # ── Create tenant databases ─────────────────────────────────────
    print("\nCreating tenant databases...")
    for name, docs in buckets.items():
        db = client[name]
        n  = insert_batched(db.movies, docs)
        db.config.insert_one({
            "tenant_id":    name,
            "display_name": TENANTS[name]["display_name"],
            "description":  TENANTS[name]["description"],
            "year_range":   TENANTS[name]["year_range"],
            "movie_count":  n,
            "plan":         "enterprise",
            "active":       True,
        })
        print(f"  {name:<22}  {n:>7,} movies + config  ✓")

    # ── Create Atlas database users ─────────────────────────────────
    has_api_creds = all([PUBLIC_KEY, PRIVATE_KEY, PROJECT_ID])
    if not has_api_creds:
        print("\nAtlas API credentials not configured — skipping database user creation.")
        print("Set ATLAS_PUBLIC_KEY, ATLAS_PRIVATE_KEY, and ATLAS_PROJECT_ID in .env")
        print("and re-run to create scoped database users for the RBAC demo.")
    else:
        print("\nCreating Atlas database users...")
        for name, meta in TENANTS.items():
            username = f"{name}_app"
            password = os.environ.get(meta["password_env"], "")
            if not password:
                print(f"  {username:<28}  SKIPPED — {meta['password_env']} not set in .env")
                continue
            status = create_atlas_user(username, password, name)
            print(f"  {username:<28}  {status}  (read → {name})")

    print("\nSetup complete. Run demo.py to explore tenant isolation.")
    client.close()


if __name__ == "__main__":
    main()
