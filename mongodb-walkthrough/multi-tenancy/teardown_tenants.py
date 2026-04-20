"""
Removes the three tenant databases and their scoped Atlas database users.

Databases dropped:
  classicflix, millenniumstream, modernplex

Atlas users deleted (requires API credentials in .env):
  classicflix_app, millenniumstream_app, modernplex_app

sample_mflix is never modified.

Usage:
  python3 teardown_tenants.py           # loads .env from current directory
  python3 teardown_tenants.py my.env    # loads a specific env file
"""

import os
import sys
import requests
from pymongo import MongoClient
from requests.auth import HTTPDigestAuth
from dotenv import load_dotenv

env_file = sys.argv[1] if len(sys.argv) > 1 else ".env"
if not os.path.exists(env_file):
    print(f"ERROR: env file '{env_file}' not found.")
    sys.exit(1)

load_dotenv(env_file, override=True)

MONGODB_URI  = os.environ["MONGODB_URI"]
PUBLIC_KEY   = os.environ.get("ATLAS_PUBLIC_KEY", "")
PRIVATE_KEY  = os.environ.get("ATLAS_PRIVATE_KEY", "")
PROJECT_ID   = os.environ.get("ATLAS_PROJECT_ID", "")

TENANT_DBS   = ["classicflix", "millenniumstream", "modernplex"]
TENANT_USERS = ["classicflix_app", "millenniumstream_app", "modernplex_app"]

BASE_URL = "https://cloud.mongodb.com/api/atlas/v2"
AUTH     = HTTPDigestAuth(PUBLIC_KEY, PRIVATE_KEY) if PUBLIC_KEY else None
HEADERS  = {
    "Content-Type": "application/json",
    "Accept": "application/vnd.atlas.2023-01-01+json",
}


def delete_atlas_user(username):
    url  = f"{BASE_URL}/groups/{PROJECT_ID}/databaseUsers/admin/{username}"
    resp = requests.delete(url, auth=AUTH, headers=HEADERS)
    if resp.status_code == 404:
        return "not found"
    if not resp.ok:
        raise RuntimeError(f"Atlas API error {resp.status_code}: {resp.text}")
    return "deleted"


def main():
    client      = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)
    existing    = client.list_database_names()
    present_dbs = [db for db in TENANT_DBS if db in existing]
    has_api     = all([PUBLIC_KEY, PRIVATE_KEY, PROJECT_ID])

    if not present_dbs:
        print("No tenant databases found. Nothing to do.")
        client.close()
        return

    # ── Show what will be removed ───────────────────────────────────
    print("The following will be permanently removed:\n")
    for db_name in present_dbs:
        count = client[db_name].movies.estimated_document_count()
        print(f"  Database   : {db_name}  ({count:,} movies)")
    if has_api:
        for u in TENANT_USERS:
            print(f"  Atlas user : {u}")
    print()
    print("sample_mflix will NOT be affected.\n")

    confirm = input("Type 'yes' to confirm teardown: ").strip().lower()
    if confirm != "yes":
        print("Aborted.")
        sys.exit(0)

    # ── Delete Atlas database users ─────────────────────────────────
    if has_api:
        print("\nDeleting Atlas database users...")
        for username in TENANT_USERS:
            status = delete_atlas_user(username)
            print(f"  {username:<28}  {status}")
    else:
        print("\nAtlas API credentials not set — skipping user deletion.")
        print("Delete classicflix_app, millenniumstream_app, modernplex_app")
        print("manually in Atlas UI → Database Access if they exist.")

    # ── Drop tenant databases ───────────────────────────────────────
    print("\nDropping tenant databases...")
    for db_name in TENANT_DBS:
        if db_name in existing:
            client.drop_database(db_name)
            print(f"  {db_name:<22}  dropped")
        else:
            print(f"  {db_name:<22}  not found, skipping")

    print("\nTeardown complete. sample_mflix is unchanged.")
    client.close()


if __name__ == "__main__":
    main()
