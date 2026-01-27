import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

def search_movies(query: str, limit: int = 5):
    client = MongoClient(
        os.environ["MONGODB_URI"],
        serverSelectionTimeoutMS=10000
    )
    
    try:
        coll = client[os.environ["DB_NAME"]][os.environ["COLLECTION_NAME"]]
        
        pipeline = [
            {
                "$search": {
                    "index": os.environ["SEARCH_INDEX"],
                    "text": {
                        "query": query,
                        "path": ["title", "plot"]
                    }
                }
            },
            {"$limit": limit},
            {"$project": {"title": 1, "year": 1, "score": {"$meta": "searchScore"}}}
        ]
        
        return list(coll.aggregate(pipeline))
    finally:
        client.close()


if __name__ == "__main__":
    query = os.environ.get("QUERY", "test")
    results = search_movies(query)
    
    for doc in results:
        print(f"{doc['title']} ({doc['year']}) - Score: {doc['score']:.2f}")