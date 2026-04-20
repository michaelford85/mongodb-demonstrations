"""
Deletes an Atlas Online Archive rule and its associated federated instance.

Rehydration (optional but recommended):
  Before deleting the archive, the script can restore archived documents back
  to the live cluster.  It reads from the federated endpoint (FEDERATED_URI),
  filters for documents that match the archive criteria, and inserts them into
  the live cluster (MONGODB_URI) in batches.  Deleting the archive without
  rehydrating first permanently removes the archived data from cloud object
  storage — it cannot be recovered afterwards.

Usage:
  python3 teardown_archive.py              # loads .env from current directory
  python3 teardown_archive.py my.env       # loads a specific env file

Which archive gets deleted:
  · If ARCHIVE_ID is set in the env file, that archive is targeted directly.
  · If ARCHIVE_ID is not set and only one archive exists on the cluster,
    that archive is targeted after confirmation.
  · If ARCHIVE_ID is not set and multiple archives exist, the script lists
    them and exits — set ARCHIVE_ID in your env file and re-run.
"""

import os
import sys
import requests
from pymongo import MongoClient
from pymongo.errors import BulkWriteError
from requests.auth import HTTPDigestAuth
from dotenv import load_dotenv

# Accept an optional path to a .env file as the first argument.
env_file = sys.argv[1] if len(sys.argv) > 1 else ".env"
if not os.path.exists(env_file):
    print(f"ERROR: env file '{env_file}' not found.")
    sys.exit(1)

load_dotenv(env_file, override=True)

PUBLIC_KEY    = os.environ["ATLAS_PUBLIC_KEY"]
PRIVATE_KEY   = os.environ["ATLAS_PRIVATE_KEY"]
PROJECT_ID    = os.environ["ATLAS_PROJECT_ID"]
CLUSTER_NAME  = os.environ["CLUSTER_NAME"]
ARCHIVE_ID    = os.environ.get("ARCHIVE_ID", "")
MONGODB_URI   = os.environ.get("MONGODB_URI", "")
FEDERATED_URI = os.environ.get("FEDERATED_URI", "")
DB_NAME       = os.environ.get("DB_NAME", "sample_mflix")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "movies")
CUTOFF_YEAR   = int(os.environ.get("ARCHIVE_CUTOFF_YEAR", "2001"))

BASE_URL = "https://cloud.mongodb.com/api/atlas/v2"
AUTH     = HTTPDigestAuth(PUBLIC_KEY, PRIVATE_KEY)
HEADERS  = {
    "Content-Type": "application/json",
    "Accept": "application/vnd.atlas.2023-01-01+json",
}

BATCH_SIZE = 500

# Archive criteria — must match what setup_archive.py used.
ARCHIVE_QUERY = {
    "$or": [
        {"year": {"$lt": CUTOFF_YEAR}},
        {"year": {"$type": "string"}},
    ]
}


def list_archives():
    url = f"{BASE_URL}/groups/{PROJECT_ID}/clusters/{CLUSTER_NAME}/onlineArchives"
    resp = requests.get(url, auth=AUTH, headers=HEADERS)
    if not resp.ok:
        raise RuntimeError(f"Atlas API error {resp.status_code}: {resp.text}")
    return resp.json().get("results", [])


def delete_archive(archive_id):
    url = f"{BASE_URL}/groups/{PROJECT_ID}/clusters/{CLUSTER_NAME}/onlineArchives/{archive_id}"
    resp = requests.delete(url, auth=AUTH, headers=HEADERS)
    if not resp.ok:
        raise RuntimeError(f"Atlas API error {resp.status_code}: {resp.text}")


def print_archive(a, index=None):
    prefix = f"  [{index}]" if index is not None else "  "
    criteria = a.get("criteria", {})
    ctype = criteria.get("type", "unknown")
    if ctype == "CUSTOM":
        criteria_str = f"CUSTOM  query={criteria.get('query', '')}"
    elif ctype == "DATE":
        criteria_str = (
            f"DATE  field={criteria.get('dateField')}  "
            f"expireAfterDays={criteria.get('expireAfterDays')}"
        )
    else:
        criteria_str = str(criteria)
    print(f"{prefix} ID       : {a['_id']}")
    print(f"      State    : {a.get('state', 'unknown')}")
    print(f"      DB/Coll  : {a.get('dbName')}.{a.get('collName')}")
    print(f"      Criteria : {criteria_str}")


def rehydrate():
    """
    Restore archived documents from the federated endpoint back to the live
    cluster.  Returns True if rehydration ran (even if 0 documents were found),
    False if it was skipped due to missing config.
    """
    if not FEDERATED_URI:
        print("  FEDERATED_URI not set — cannot rehydrate.")
        print("  Add FEDERATED_URI to your .env and re-run if you want to restore data first.")
        return False
    if not MONGODB_URI:
        print("  MONGODB_URI not set — cannot rehydrate.")
        return False

    print("  Connecting to federated endpoint to count archived documents...")
    try:
        fed_client = MongoClient(FEDERATED_URI, serverSelectionTimeoutMS=30_000)
        fed_client.admin.command("ping")
        fed_coll = fed_client[DB_NAME][COLLECTION_NAME]

        total = fed_coll.count_documents(ARCHIVE_QUERY)
        print(f"  Archived documents found : {total:,}")

        if total == 0:
            print("  Nothing to restore.")
            fed_client.close()
            return True

        live_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)
        live_coll = live_client[DB_NAME][COLLECTION_NAME]

        print(f"  Restoring in batches of {BATCH_SIZE}...")
        cursor = fed_coll.find(ARCHIVE_QUERY)
        batch = []
        restored = 0
        duplicates = 0

        for doc in cursor:
            batch.append(doc)
            if len(batch) >= BATCH_SIZE:
                try:
                    live_coll.insert_many(batch, ordered=False)
                    restored += len(batch)
                except BulkWriteError as e:
                    inserted = e.details.get("nInserted", 0)
                    restored += inserted
                    duplicates += len(batch) - inserted
                batch = []
                print(f"  Progress : {restored:,} restored, {duplicates:,} already present...")

        if batch:
            try:
                live_coll.insert_many(batch, ordered=False)
                restored += len(batch)
            except BulkWriteError as e:
                inserted = e.details.get("nInserted", 0)
                restored += inserted
                duplicates += len(batch) - inserted

        print(f"\n  Rehydration complete.")
        print(f"    Restored  : {restored:,} documents")
        if duplicates:
            print(f"    Skipped   : {duplicates:,} documents already on live cluster")

        fed_client.close()
        live_client.close()
        return True

    except Exception as e:
        print(f"  Rehydration failed: {e}")
        return False


def main():
    print(f"Loading config from : {env_file}")
    print(f"Cluster             : {CLUSTER_NAME}")
    print(f"Project             : {PROJECT_ID}")
    if ARCHIVE_ID:
        print(f"Target archive      : {ARCHIVE_ID}  (from ARCHIVE_ID in env)")
    print()

    archives = list_archives()

    if not archives:
        print("No archive rules found on this cluster. Nothing to do.")
        return

    # ── Resolve which archive to delete ────────────────────────────
    if ARCHIVE_ID:
        target = next((a for a in archives if a["_id"] == ARCHIVE_ID), None)
        if not target:
            print(f"ERROR: Archive ID '{ARCHIVE_ID}' not found on cluster '{CLUSTER_NAME}'.")
            print("\nArchives that do exist:")
            for a in archives:
                print_archive(a)
            sys.exit(1)

    elif len(archives) == 1:
        target = archives[0]

    else:
        print(f"Multiple archives found on '{CLUSTER_NAME}'. Set ARCHIVE_ID in your env file")
        print("to target one specifically, then re-run.\n")
        print(f"Found {len(archives)} archives:\n")
        for i, a in enumerate(archives):
            print_archive(a, index=i)
            print()
        sys.exit(1)

    # ── Show what will be deleted ───────────────────────────────────
    print("Archive to be deleted:")
    print_archive(target)
    print()
    print("WARNING: Deleting this archive also removes the associated Data Federation")
    print("         endpoint. Any data still in cloud object storage will be permanently")
    print("         deleted and cannot be recovered.")
    print()

    # ── Offer rehydration before deletion ──────────────────────────
    if FEDERATED_URI and MONGODB_URI:
        answer = input("Restore archived documents back to the live cluster before deleting? [y/N]: ").strip().lower()
        if answer == "y":
            print()
            rehydrate()
            print()
        else:
            print("Skipping rehydration — archived data will be permanently deleted.\n")
    else:
        missing = []
        if not MONGODB_URI:
            missing.append("MONGODB_URI")
        if not FEDERATED_URI:
            missing.append("FEDERATED_URI")
        print(f"Note: {' and '.join(missing)} not set — rehydration unavailable.")
        print("      Archived data will be permanently deleted on teardown.\n")

    # ── Confirm and delete ──────────────────────────────────────────
    confirm = input(f"Type the archive ID to confirm deletion: ").strip()
    if confirm != target["_id"]:
        print("ID did not match. Aborting.")
        sys.exit(1)

    print()
    print("Deleting archive rule...")
    delete_archive(target["_id"])
    print(f"Done. Archive {target['_id']} has been deleted.")
    print("The associated federated endpoint will be removed by Atlas shortly.")


if __name__ == "__main__":
    main()
