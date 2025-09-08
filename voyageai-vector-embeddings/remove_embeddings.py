#!/usr/bin/env python3
import os
import sys
import time
from typing import List, Dict

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError
import voyageai

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")

if not MONGODB_URI:
    print("ERROR: MONGODB_URI not set. Set it in your environment or .env file.", file=sys.stderr)
    sys.exit(1)
if not VOYAGE_API_KEY:
    print("ERROR: VOYAGE_API_KEY not set. Set it in your environment or .env file.", file=sys.stderr)
    sys.exit(1)

DB_NAME = os.getenv("DB_NAME", "sample_mflix")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "movies")
VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-3.5")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "128"))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# Connect clients
client = voyageai.Client(api_key=VOYAGE_API_KEY)
mongo = MongoClient(
    os.getenv("MONGODB_URI"),
    tls=True,
    tlsCertificateKeyFile=os.getenv("MONGODB_CERT")
)
coll = mongo[DB_NAME][COLLECTION_NAME]



def main():

    result = coll.update_many(
        {},
        {"$unset": {"plot_embedding": ""}}
    )

    print(f"Matched {result.matched_count} documents.")
    print(f"Modified {result.modified_count} documents.")

if __name__ == "__main__":
    main()
