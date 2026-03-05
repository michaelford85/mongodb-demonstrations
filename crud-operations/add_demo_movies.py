import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient

DEMO_TAG = "crud-flex-schema-demo-v1"


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def build_demo_movies():
    now = datetime.now(timezone.utc)
    return [
        {
            "demoMovieId": "demo-001",
            "title": "Skyline Chase",
            "year": 2023,
            "rated": "PG-13",
            "genres": ["Action", "Adventure"],
            "plot": "A courier races across a floating city to stop a power-grid collapse.",
            "imdb": {"rating": 7.2, "votes": 18421},
            "demoTag": DEMO_TAG,
            "flexField": "This field does not exist on most sample_mflix movies.",
            "streamingAvailability": ["StreamFlix", "CineNow"],
            "createdAt": now,
        },
        {
            "demoMovieId": "demo-002",
            "title": "Midnight Orchard",
            "year": 2021,
            "rated": "R",
            "genres": ["Drama", "Mystery"],
            "plot": "A botanist uncovers coded messages hidden in a dying apple grove.",
            "imdb": {"rating": 6.8, "votes": 9722},
            "demoTag": DEMO_TAG,
            "flexField": "Custom metadata to demonstrate flexible schema.",
            "criticNotes": {"tone": "melancholic", "festivalPick": True},
            "createdAt": now,
        },
        {
            "demoMovieId": "demo-003",
            "title": "Orbit Cafe",
            "year": 2024,
            "rated": "PG",
            "genres": ["Comedy", "Sci-Fi"],
            "plot": "A struggling diner on a moon base becomes a diplomatic hotspot.",
            "imdb": {"rating": 7.6, "votes": 12509},
            "demoTag": DEMO_TAG,
            "streamingAvailability": ["Nova+"],
            "createdAt": now,
        },
        {
            "demoMovieId": "demo-004",
            "title": "Paper Lantern Code",
            "year": 2020,
            "rated": "PG-13",
            "genres": ["Thriller"],
            "plot": "A codebreaker follows a chain of lantern symbols across four cities.",
            "imdb": {"rating": 7.0, "votes": 14118},
            "demoTag": DEMO_TAG,
            "criticNotes": {"tone": "tense", "festivalPick": False},
            "createdAt": now,
        },
        {
            "demoMovieId": "demo-005",
            "title": "Borrowed Sunlight",
            "year": 2022,
            "rated": "PG",
            "genres": ["Family", "Fantasy"],
            "plot": "Two siblings try to return stolen daylight before winter locks in forever.",
            "imdb": {"rating": 6.9, "votes": 8830},
            "demoTag": DEMO_TAG,
            "flexField": "Another non-standard field for schema flexibility.",
            "createdAt": now,
        },
    ]


def main():
    load_dotenv()

    uri = require_env("MONGODB_URI")
    db_name = require_env("DB_NAME")
    collection_name = require_env("COLLECTION_NAME")

    client = MongoClient(uri)
    try:
        collection = client[db_name][collection_name]
        demo_movies = build_demo_movies()

        existing_ids = set(
            collection.distinct(
                "demoMovieId",
                {
                    "demoTag": DEMO_TAG,
                    "demoMovieId": {"$in": [m["demoMovieId"] for m in demo_movies]},
                },
            )
        )
        to_insert = [m for m in demo_movies if m["demoMovieId"] not in existing_ids]

        if not to_insert:
            print("No new demo movies inserted. All demoMovieId values already exist.")
            return

        result = collection.insert_many(to_insert)
        print(f"Inserted {len(result.inserted_ids)} demo movies into {db_name}.{collection_name}.")
        print(f"Demo tag: {DEMO_TAG}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
