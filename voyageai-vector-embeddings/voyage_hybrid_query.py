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
                truncation=True,
                output_dimension=dimensions
            )
            # voyageai returns `.embeddings` on response
    return resp.embeddings[0]
 
def make_compute_score_doc(priority, score_field_name):
    return {
        "$addFields": {
            score_field_name: {
                "$divide": [
                    1.0,
                    {
                        "$add": ["$rank", priority, 1] 
                    }
                ]
            }
        }
    }

def make_projection_doc(score_field_name):
    return {
        "$project": {
            score_field_name: 1,
            "_id": "$docs._id",
            "title": "$docs.title",
            "plot": "$docs.plot",
            "year": "$docs.year"
        }
    }


def main():

    #Define k values for each search method
    vector_priority = int(os.getenv("VECTOR_PRIORITY", 1))
    text_priority = int(os.getenv("TEXT_PRIORITY", 1))
    limit = int(os.getenv("QUERY_LIMIT", 10))
    overrequest_factor = 10

    query = os.getenv("QUERY", "A movie about superheroes with great powers")

    query_embedding = get_embeddings([query], VOYAGE_MODEL, EMBEDDING_DIM, VOYAGE_API_KEY)

    # print("Query embedding:", query_embedding)

    vector_search = {
        "$vectorSearch": {
            "numCandidates": limit * overrequest_factor,
            "path": "plot_embedding",
            "index": "plot_embedding_index",
            "limit": limit,
            "queryVector": query_embedding
        }
    }

    # Group all documents together into a single array
    make_array = {
        "$group": {
            "_id": None,
            "docs": {"$push": "$$ROOT"}
        }
    }

    add_rank ={ 
        "$unwind": {
            "path": "$docs",
            "includeArrayIndex": "rank"
        }
    }

    text_search = {
        "$search": {
            "index": "plot_text_index",
            "text": {
                "query": query,
                "path": "fullplot"
            }
        }
    }

    limit_results = {
        "$limit" : limit
    }

    combine_search_results = {
        "$group": {
            "_id":        "$_id",
            "vs_score":   {"$max":    "$vs_score"},
            "ts_score":   {"$max":    "$ts_score"},
            "title":      {"$first":  "$title"},
            "plot":       {"$first":  "$plot"},
            "year":       {"$first":  "$year"}
        }
    }

    project_combined_results = {
        "$project": {
            "_id":        1,
            "title":      1,
            "plot":       1,
            "year":       1,
            "score": {
                "$let": {
                    "vars": {
                        "vs_score":  { "$ifNull":  ["$vs_score", 0] },
                        "ts_score":  { "$ifNull":  ["$ts_score", 0] }
                    },
                    "in": { "$add": ["$$vs_score", "$$ts_score"] }
                }
            }
        }
    }

    sort_results = {
        "$sort": { "score": -1}
    }

    pipeline = [
        vector_search,
        make_array,
        add_rank,
        make_compute_score_doc(vector_priority, "vs_score"),
        make_projection_doc("vs_score"),
        {
            "$unionWith": { "coll": "movies",
                "pipeline": [
                    text_search,
                    limit_results,
                    make_array,
                    add_rank,
                    make_compute_score_doc(text_priority, "ts_score"),
                    make_projection_doc("ts_score")
                ]
            }
        },
        combine_search_results,
        project_combined_results,
        sort_results,
        limit_results
    ]

    results = coll.aggregate(pipeline)

    for doc in results:
        print(doc)

if __name__ == "__main__":
    main()
