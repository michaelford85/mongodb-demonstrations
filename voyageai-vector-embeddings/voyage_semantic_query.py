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
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))

if not MONGODB_URI:
    print("ERROR: MONGODB_URI not set. Set it in your environment or .env file.", file=sys.stderr)
    sys.exit(1)
if not VOYAGE_API_KEY:
    print("ERROR: VOYAGE_API_KEY not set. Set it in your environment or .env file.", file=sys.stderr)
    sys.exit(1)

DB_NAME = os.getenv("DB_NAME", "sample_mflix")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "movies")
VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-3.5")

# Connect VoyageAI and MongoDB clients
client = voyageai.Client(api_key=VOYAGE_API_KEY)
mongo = MongoClient(
    os.getenv("MONGODB_URI"),
    tls=True,
    tlsCertificateKeyFile=os.getenv("MONGODB_CERT")
)
coll = mongo[DB_NAME][COLLECTION_NAME]

def get_embeddings(texts, model, dimensions, api_key):
    resp = client.embed(
                texts=texts,
                model=model,
                input_type="document",
                # input_type="query",
                truncation=True,
                output_dimension=dimensions
            )
            # voyageai returns `.embeddings` on response
    return resp.embeddings[0]
 
def main():

    query = os.getenv("QUERY", "A movie about superheroes with great powers")

    query_embedding = get_embeddings([query], VOYAGE_MODEL, EMBEDDING_DIM, VOYAGE_API_KEY)

    print("Query embedding:", query_embedding)

    semantic_query = {
        "$vectorSearch": {
            "numCandidates": 50,
            "path": "plot_embedding",
            "index": "plot_embedding_index",
            "limit": int(os.getenv("QUERY_LIMIT", 5)),
            "queryVector": query_embedding
        }
    }

    semantic_query_projection = {
        "$project": {
            "title": 1,
            "plot": 1,
            "score":  {
                "$meta": "vectorSearchScore"
            }
        }
    }

    pipeline = [
        semantic_query, semantic_query_projection
    ]

    # pipeline = [
    #     semantic_query_projection
    # ]

    results = coll.aggregate(pipeline)

    for doc in results:
        print(doc)

if __name__ == "__main__":
    main()
