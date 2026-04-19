"""
Configures an Atlas Online Archive rule on sample_mflix.movies.

Documents with a 'released' date older than ARCHIVE_EXPIRE_AFTER_DAYS days are
automatically moved to cold storage by Atlas on a daily schedule. This script
creates that rule via the Atlas Admin API; the actual archiving runs async.

Run this once. Re-running safely detects and reports an existing rule.
"""

import os
import sys
import requests
from requests.auth import HTTPDigestAuth
from dotenv import load_dotenv

load_dotenv()

PUBLIC_KEY = os.environ["ATLAS_PUBLIC_KEY"]
PRIVATE_KEY = os.environ["ATLAS_PRIVATE_KEY"]
PROJECT_ID = os.environ["ATLAS_PROJECT_ID"]
CLUSTER_NAME = os.environ["CLUSTER_NAME"]
DB_NAME = os.environ.get("DB_NAME", "sample_mflix")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "movies")
EXPIRE_AFTER_DAYS = int(os.environ.get("ARCHIVE_EXPIRE_AFTER_DAYS", "9000"))

BASE_URL = "https://cloud.mongodb.com/api/atlas/v2"
AUTH = HTTPDigestAuth(PUBLIC_KEY, PRIVATE_KEY)
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/vnd.atlas.2023-01-01+json",
}


def list_archives():
    url = f"{BASE_URL}/groups/{PROJECT_ID}/clusters/{CLUSTER_NAME}/onlineArchives"
    resp = requests.get(url, auth=AUTH, headers=HEADERS)
    resp.raise_for_status()
    return resp.json().get("results", [])


def create_archive():
    url = f"{BASE_URL}/groups/{PROJECT_ID}/clusters/{CLUSTER_NAME}/onlineArchives"
    body = {
        "dbName": DB_NAME,
        "collName": COLLECTION_NAME,
        "criteria": {
            "type": "DATE",
            "dateField": "released",
            "dateFormat": "ISODATE",
            "expireAfterDays": EXPIRE_AFTER_DAYS,
        },
        "partitionFields": [
            {"fieldName": "released", "order": 0},
            {"fieldName": "title", "order": 1},
        ],
        "schedule": {
            "type": "DAILY",
            "hour": 0,
            "minute": 0,
        },
    }
    resp = requests.post(url, auth=AUTH, headers=HEADERS, json=body)
    resp.raise_for_status()
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
        print(f"  ID     : {a['_id']}")
        print(f"  State  : {a['state']}")
        print(f"  Field  : {a['criteria']['dateField']} older than {a['criteria']['expireAfterDays']} days")
        print(f"\nOnce the state is ACTIVE and archiving has run, set FEDERATED_URI in .env")
        print(f"and run query_demo.py.")
        return

    print(f"Creating archive rule:")
    print(f"  Collection : {DB_NAME}.{COLLECTION_NAME}")
    print(f"  Field      : released")
    print(f"  Threshold  : older than {EXPIRE_AFTER_DAYS} days")
    print()

    result = create_archive()

    print(f"Archive rule created.")
    print(f"  ID     : {result['_id']}")
    print(f"  State  : {result['state']}")
    print()
    print("Next steps:")
    print("  1. Atlas will begin archiving on its next daily run (typically within 24 hours).")
    print("  2. In Atlas UI → Data Federation, a federated endpoint is created automatically.")
    print("  3. Copy that endpoint's connection string into FEDERATED_URI in .env.")
    print("  4. Run query_demo.py to compare live vs. archived query performance.")


if __name__ == "__main__":
    main()
