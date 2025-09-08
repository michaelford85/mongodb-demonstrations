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

if not MONGODB_URI:
    print("ERROR: MONGODB_URI not set. Set it in your environment or .env file.", file=sys.stderr)
    sys.exit(1)

DB_NAME = os.getenv("DB_NAME", "sample_mflix")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "movies")
VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-3.5")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "128"))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# Connect MongoDB client
mongo = MongoClient(
    os.getenv("MONGODB_URI"),
    tls=True,
    tlsCertificateKeyFile=os.getenv("MONGODB_CERT")
)
coll = mongo[DB_NAME][COLLECTION_NAME]

def ensure_vector_index():
    """
    Create/ensure an Atlas Vector Search index for plot_embedding with the right dimension.
    Uses name: plot_embedding_index
    """
    try:
        # Check if exists
        existing = mongo[DB_NAME].command({
            "listSearchIndexes": COLLECTION_NAME,
            "name": "plot_embedding_index"
        }).get("indexes", [])
    except PyMongoError:
        # Older drivers/servers may not support listSearchIndexes via command; ignore and try to create
        existing = []

    if existing:
        # Optionally verify dims/similarity, but we'll skip strict checks
        return
    
    index_def = {
        "name": "plot_embedding_index",
        "type": "vectorSearch",  
        "definition": {
            "fields": [
                {
                    "type": "vector",
                    "path": "plot_embedding",
                    "numDimensions": EMBEDDING_DIM,
                    "similarity": "cosine"
                },
                {
                    "type": "filter",
                    "path": "year"
                }
            ]
        }
    }

    try:
        mongo[DB_NAME][COLLECTION_NAME].create_search_index(index_def)
        print(f"Created Vector Search index 'plot_embedding_index' with dims={EMBEDDING_DIM}")
    except PyMongoError as e:
        # Non-fatal: user may lack permissions, or index already exists
        print(f"WARN: Could not create vector index automatically: {e}", file=sys.stderr)


def ensure_search_index():
    """
    Create/ensure an Atlas Search index for plot with the right dimension.
    Uses name: plot_text_index
    """
    try:
        # Check if exists
        existing = mongo[DB_NAME].command({
            "listSearchIndexes": COLLECTION_NAME,
            "name": "plot_text_index"
        }).get("indexes", [])
    except PyMongoError:
        # Older drivers/servers may not support listSearchIndexes via command; ignore and try to create
        existing = []

    if existing:
        # Optionally verify dims/similarity, but we'll skip strict checks
        return
    
    index_def = {
        "name": "plot_text_index",
        "type": "search",  
        "definition": {
            "mappings": {
                "dynamic": True,
                "fields": {
                    "fullplot": {
                        "type": "string"
                    }
                }
            }
        }
    }
    try:
        mongo[DB_NAME][COLLECTION_NAME].create_search_index(index_def)
        print(f"Created Vector Search index 'plot_text_index'")
    except PyMongoError as e:
        # Non-fatal: user may lack permissions, or index already exists
        print(f"WARN: Could not create search index automatically: {e}", file=sys.stderr)


def main():
    ensure_search_index()
    print(f"Done. Full Text Search Index for full_plot field created")
    ensure_vector_index()
    print(f"Done. Vector Search Index for plot_embedding field created")

if __name__ == "__main__":
    main()