"""
Drops the demo database from Atlas and removes the local S3 stand-in directory.

Does not touch any other database on the cluster. Asks for confirmation
before deleting.
"""

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGODB_URI = os.environ["MONGODB_URI"]
DB_NAME     = os.environ.get("DB_NAME", "atlas_databricks_demo")
LOCAL_DIR   = Path(__file__).parent / "_s3_export"


def main():
    print(f"This will drop the '{DB_NAME}' database on the Atlas cluster")
    print(f"and remove the local export directory {LOCAL_DIR} if present.")
    answer = input("Proceed? [y/N]: ").strip().lower()
    if answer != "y":
        print("Aborted.")
        return

    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)
    client.drop_database(DB_NAME)
    print(f"  Dropped database: {DB_NAME}")
    client.close()

    if LOCAL_DIR.exists():
        shutil.rmtree(LOCAL_DIR)
        print(f"  Removed: {LOCAL_DIR}")
    else:
        print(f"  No local export directory to remove.")

    print("Teardown complete.")


if __name__ == "__main__":
    main()
