"""
Configures an Atlas Online Archive rule on sample_mflix.movies.

Uses a CUSTOM criteria on the integer 'year' field so the cutoff is universal
— every document in the collection has a year, unlike the 'released' date field
which is absent on a subset of documents.

Movies with year < ARCHIVE_CUTOFF_YEAR are archived to cold storage on Atlas's
daily schedule. This script creates that rule via the Atlas Admin API.

Before creating the archive rule the script creates an index on the 'year'
field. This index serves two purposes:
  1. The Atlas archive daemon uses it to efficiently identify documents that
     match the archive criteria without scanning the entire collection.
  2. Queries against the live (hot) tier after archiving — e.g. year >= 2001 —
     use the same index, keeping hot-tier reads fast.

Run once. Re-running safely detects and reports an existing rule.
"""

import json
import os
import requests
from pymongo import MongoClient, ASCENDING
from requests.auth import HTTPDigestAuth
from dotenv import load_dotenv

load_dotenv()

PUBLIC_KEY           = os.environ["ATLAS_PUBLIC_KEY"]
PRIVATE_KEY          = os.environ["ATLAS_PRIVATE_KEY"]
PROJECT_ID           = os.environ["ATLAS_PROJECT_ID"]
CLUSTER_NAME         = os.environ["CLUSTER_NAME"]
MONGODB_URI          = os.environ["MONGODB_URI"]
DB_NAME              = os.environ.get("DB_NAME", "sample_mflix")
COLLECTION_NAME      = os.environ.get("COLLECTION_NAME", "movies")
CUTOFF_YEAR          = int(os.environ.get("ARCHIVE_CUTOFF_YEAR", "2001"))
ARCHIVE_CLOUD_PROVIDER = os.environ.get("ARCHIVE_CLOUD_PROVIDER", "")
ARCHIVE_REGION       = os.environ.get("ARCHIVE_REGION", "")

BASE_URL = "https://cloud.mongodb.com/api/atlas/v2"
AUTH     = HTTPDigestAuth(PUBLIC_KEY, PRIVATE_KEY)
HEADERS  = {
    "Content-Type": "application/json",
    "Accept": "application/vnd.atlas.2023-01-01+json",
}


def ensure_index():
    """Create an index on the archive field if one does not already exist."""
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)
    coll = client[DB_NAME][COLLECTION_NAME]
    existing = {idx["name"] for idx in coll.list_indexes()}
    if "year_1" in existing:
        print("  Index on 'year' already exists — skipping creation.")
    else:
        coll.create_index([("year", ASCENDING)], name="year_1")
        print("  Index on 'year' created.")
    client.close()


def list_archives():
    url = f"{BASE_URL}/groups/{PROJECT_ID}/clusters/{CLUSTER_NAME}/onlineArchives"
    resp = requests.get(url, auth=AUTH, headers=HEADERS)
    if not resp.ok:
        raise RuntimeError(f"Atlas API error {resp.status_code}: {resp.text}")
    return resp.json().get("results", [])


def create_archive():
    url = f"{BASE_URL}/groups/{PROJECT_ID}/clusters/{CLUSTER_NAME}/onlineArchives"
    # The CUSTOM query archives documents where year is a number < CUTOFF_YEAR
    # OR where year is stored as a string.  A small subset of sample_mflix.movies
    # has garbled string values (e.g. "1981è", "1994è1998") instead of integers;
    # those documents predate the cutoff but would be skipped by a numeric-only
    # comparison because BSON sorts all strings after all numbers.
    archive_query = {
        "$or": [
            {"year": {"$lt": CUTOFF_YEAR}},
            {"year": {"$type": "string"}},
        ]
    }

    body = {
        "dbName": DB_NAME,
        "collName": COLLECTION_NAME,
        "criteria": {
            "type": "CUSTOM",
            "query": json.dumps(archive_query),
        },
        # Partition fields define how archived data is organised in object
        # storage.  They act as an index for the cold tier — queries that
        # filter on 'year' can skip irrelevant partitions without scanning
        # every archived object.  Order matters: the first field produces the
        # coarsest-grained partitions (choose the field you filter on most).
        "partitionFields": [
            {"fieldName": "year",  "order": 0},
            {"fieldName": "title", "order": 1},
        ],
    }
    if ARCHIVE_CLOUD_PROVIDER and ARCHIVE_REGION:
        body["dataProcessRegion"] = {
            "cloudProvider": ARCHIVE_CLOUD_PROVIDER,
            "region": ARCHIVE_REGION,
        }
    resp = requests.post(url, auth=AUTH, headers=HEADERS, json=body)
    if not resp.ok:
        raise RuntimeError(f"Atlas API error {resp.status_code}: {resp.text}")
    return resp.json()


def main():
    print(f"Checking existing archives on {CLUSTER_NAME} / {DB_NAME}.{COLLECTION_NAME} ...")

    existing = [
        a for a in list_archives()
        if a.get("dbName") == DB_NAME and a.get("collName") == COLLECTION_NAME
    ]

    if existing:
        a = existing[0]
        print(f"\nArchive rule already exists — nothing to do.")
        print(f"  ID       : {a['_id']}")
        print(f"  State    : {a['state']}")
        print(f"  Criteria : {a.get('criteria', {})}")
        print(f"\nOnce the state is ACTIVE and archiving has run, set FEDERATED_URI in .env")
        print(f"and run query_demo.py.")
        return

    # ── Step 1: create index on the archive field ───────────────────
    print(f"\nEnsuring index on '{COLLECTION_NAME}.year' (archive + query performance)...")
    ensure_index()

    # ── Step 2: create the archive rule ────────────────────────────
    print(f"\nCreating archive rule:")
    print(f"  Collection : {DB_NAME}.{COLLECTION_NAME}")
    print(f"  Field      : year  (integer or string)")
    print(f"  Criteria   : year < {CUTOFF_YEAR}  OR  year is a string (garbled entries)")
    print(f"  Partitions : year → title  (cold-tier query index)")
    if ARCHIVE_CLOUD_PROVIDER and ARCHIVE_REGION:
        print(f"  Data region: {ARCHIVE_CLOUD_PROVIDER} / {ARCHIVE_REGION}")
    else:
        print(f"  Data region: (auto — single-region cluster)")
    print()

    result = create_archive()

    print(f"Archive rule created.")
    print(f"  ID     : {result['_id']}")
    print(f"  State  : {result['state']}")
    print()
    print("Next steps:")
    print("  1. Atlas will begin archiving on its next daily run (typically within 24 hours).")
    print("  2. In Atlas UI → Online Archive → Connect → 'Connect to Cluster and Online Archive'")
    print("     copy that connection string into FEDERATED_URI in .env.")
    print("  3. Run query_demo.py to compare live vs. archived query performance.")


if __name__ == "__main__":
    main()
