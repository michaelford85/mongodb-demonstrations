"""
Deletes an Atlas Online Archive rule and its associated federated instance.

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
from requests.auth import HTTPDigestAuth
from dotenv import load_dotenv

# Accept an optional path to a .env file as the first argument.
env_file = sys.argv[1] if len(sys.argv) > 1 else ".env"
if not os.path.exists(env_file):
    print(f"ERROR: env file '{env_file}' not found.")
    sys.exit(1)

load_dotenv(env_file, override=True)

PUBLIC_KEY  = os.environ["ATLAS_PUBLIC_KEY"]
PRIVATE_KEY = os.environ["ATLAS_PRIVATE_KEY"]
PROJECT_ID  = os.environ["ATLAS_PROJECT_ID"]
CLUSTER_NAME = os.environ["CLUSTER_NAME"]
ARCHIVE_ID  = os.environ.get("ARCHIVE_ID", "")

BASE_URL = "https://cloud.mongodb.com/api/atlas/v2"
AUTH     = HTTPDigestAuth(PUBLIC_KEY, PRIVATE_KEY)
HEADERS  = {
    "Content-Type": "application/json",
    "Accept": "application/vnd.atlas.2023-01-01+json",
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
    print(f"{prefix} ID       : {a['_id']}")
    print(f"      State    : {a.get('state', 'unknown')}")
    print(f"      DB/Coll  : {a.get('dbName')}.{a.get('collName')}")
    criteria = a.get("criteria", {})
    print(f"      Field    : {criteria.get('dateField')} older than {criteria.get('expireAfterDays')} days")


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

    # ── Confirm and delete ──────────────────────────────────────────
    print("Archive to be deleted:")
    print_archive(target)
    print()
    print("WARNING: This also removes the associated Data Federation endpoint.")
    print("         Archived data in cloud object storage will be permanently deleted.")
    print()

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
