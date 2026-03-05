import os

from dotenv import load_dotenv
from pymongo import MongoClient


def require_env_var(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def build_pipeline():
    return [
        {
            "$match": {
                "genres": {"$exists": True, "$not": {"$size": 0}},
                "imdb.rating": {"$gt": 0},
            }
        },
        {"$unwind": "$genres"},
        {
            "$group": {
                "_id": {"genre": "$genres", "title": "$title"},
                "imdbRating": {"$max": "$imdb.rating"},
            }
        },
        {
            "$setWindowFields": {
                "partitionBy": "$_id.genre",
                "sortBy": {"imdbRating": -1},
                "output": {"rank": {"$documentNumber": {}}},
            }
        },
        {"$match": {"rank": {"$lte": 3}}},
        {
            "$project": {
                "_id": 0,
                "genre": "$_id.genre",
                "title": "$_id.title",
                "imdbRating": 1,
                "rank": 1,
            }
        },
        {"$sort": {"genre": 1, "rank": 1}},
    ]


def main():
    load_dotenv()

    uri = require_env_var("MONGODB_URI")
    db_name = require_env_var("DB_NAME")
    collection_name = require_env_var("COLLECTION_NAME")

    client = MongoClient(uri)
    try:
        collection = client[db_name][collection_name]
        results = list(collection.aggregate(build_pipeline()))

        print("Top 3 movies per genre by IMDb rating:")
        current_genre = None

        if not results:
            print("No movies matched the pipeline criteria.")
            return

        for doc in results:
            genre = doc.get("genre", "Unknown")
            if genre != current_genre:
                if current_genre is not None:
                    print()
                print(f"For the genre '{genre}', the top ranked films are:")
                current_genre = genre

            title = doc.get("title", "Untitled")
            rating = doc.get("imdbRating", "N/A")
            rank = doc.get("rank", "N/A")
            print(f"  {rank}. {title} (IMDb: {rating})")
    finally:
        client.close()


if __name__ == "__main__":
    main()
