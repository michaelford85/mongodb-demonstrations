import os
import sys
import time
import pymongo
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError
from pymongo.operations import SearchIndexModel

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
FTS_INDEX_NAME = os.getenv("FTS_INDEX_NAME")
DB_NAME = os.getenv("DB_NAME")
CONNECTION_STRING = MONGODB_URI
client = pymongo.MongoClient(CONNECTION_STRING)
db = client[DB_NAME]
movies = db[os.getenv("COLLECTION_NAME")]

def ensure_search_index(collection):
    """Checks for the index and creates it if missing."""
    existing_indices = list(collection.list_search_indexes())
    index_exists = any(idx['name'] == FTS_INDEX_NAME for idx in existing_indices)

    index_definition = {
        "mappings": {
            "dynamic": False,
            "fields": {
                "title": {
                    "type": "string",
                    "analyzer": "lucene.standard"
                }
            }
        }
    }

    if not index_exists:
        print(f"Index '{FTS_INDEX_NAME}' not found. Creating it now...")
        index_model = SearchIndexModel(
            definition=index_definition, # Use the defined index
            name=FTS_INDEX_NAME
        )
        collection.create_search_index(model=index_model)
        
        print("Waiting for index to build (this can take 1-2 minutes)...")
        while True:
            # Poll for the 'queryable' status
            indices = list(collection.list_search_indexes(FTS_INDEX_NAME))
            if indices and indices[0].get("queryable"):
                print("Index is now active!")
                break
            time.sleep(5)
    else:
        print(f"Atlas Search index '{FTS_INDEX_NAME}' is ready.")

def run_benchmarks(collection, term):
    print(f"\n{'='*40}\nSearching for: '{term}'\n{'='*40}")

    # --- 1. Regex Search ---
    start_reg = datetime.now()
    reg_results = list(collection.aggregate([
        {"$match": {"title": {"$regex": term, "$options": "i"}}},
        {"$limit": 3},
        {"$project": {"title": 1, "_id": 0}}
    ]))
    end_reg = datetime.now()
    
    print(f"--- Regex Results (Time: {(end_reg - start_reg).total_seconds() * 1000:.2f}ms) ---")
    if not reg_results: print("No results found.")
    for doc in reg_results: print(f"- {doc['title']}")

    # --- 2. Atlas Search (with Fuzziness) ---
    start_fts = datetime.now()
    fts_results = list(collection.aggregate([
        {
            "$search": {
                "index": FTS_INDEX_NAME,
                "text": {
                    "query": term,
                    "path": "title",
                    "fuzzy": {"maxEdits": 2} # Allows for typos like 'Blck'
                }
            }
        },
        {"$limit": 3},
        {"$project": {"title": 1, "_id": 0, "score": {"$meta": "searchScore"}}}
    ]))
    end_fts = datetime.now()

    print(f"\n--- Atlas Search Results (Time: {(end_fts - start_fts).total_seconds() * 1000:.2f}ms) ---")
    if not fts_results: print("No results found.")
    for doc in fts_results: 
        print(f"- {doc['title']} (Score: {doc['score']:.2f})")

def main():
    try:
        client = MongoClient(CONNECTION_STRING)
        db = client[os.getenv("DB_NAME")]
        collection = db[os.getenv("COLLECTION_NAME")]

        # Step 1: Ensure the environment is ready
        ensure_search_index(collection)

        # Step 2: Run comparisons
        # This will now succeed for "Blck" because of the "fuzzy" operator
        run_benchmarks(collection, "Black Cat")
        run_benchmarks(collection, "Blck Cat")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    main()