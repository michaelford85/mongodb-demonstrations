import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient

DEMO_TAG = "change-streams-demo-v1"
PAUSE = 2  # seconds between steps so the watcher output is readable


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def step(label: str) -> None:
    print()
    print("=" * 60)
    print(f"  {label}")
    print("=" * 60)


def build_demo_movies() -> list[dict]:
    now = datetime.now(timezone.utc)
    return [
        {
            "demoMovieId": "cs-demo-001",
            "title": "Neon Horizon",
            "year": 2024,
            "rated": "PG-13",
            "genres": ["Sci-Fi", "Action"],
            "plot": "A detective uncovers a conspiracy in a city powered entirely by light.",
            "imdb": {"rating": 7.4, "votes": 10500},
            "demoTag": DEMO_TAG,
            "createdAt": now,
        },
        {
            "demoMovieId": "cs-demo-002",
            "title": "The Last Cartographer",
            "year": 2023,
            "rated": "PG",
            "genres": ["Adventure", "Drama"],
            "plot": "A mapmaker discovers that her charts have been predicting disasters.",
            "imdb": {"rating": 6.9, "votes": 8300},
            "demoTag": DEMO_TAG,
            "createdAt": now,
        },
        {
            "demoMovieId": "cs-demo-003",
            "title": "Salt and Static",
            "year": 2022,
            "rated": "R",
            "genres": ["Thriller"],
            "plot": "A radio technician intercepts a signal that was never meant to be heard.",
            "imdb": {"rating": 7.1, "votes": 12200},
            "demoTag": DEMO_TAG,
            "createdAt": now,
        },
    ]


def main() -> None:
    load_dotenv()

    uri = require_env("MONGODB_URI")
    db_name = require_env("DB_NAME")
    collection_name = require_env("COLLECTION_NAME")

    client = MongoClient(uri)
    collection = client[db_name][collection_name]

    print(f"Connected to {db_name}.{collection_name}")
    print(f"Demo tag  : {DEMO_TAG}")
    print()
    print("This script performs inserts, updates, and deletes to trigger")
    print("change stream events. Open watch.py in another terminal first.")
    print()
    input("Press Enter when the watcher is running...")

    # ------------------------------------------------------------------
    # STEP 1: Remove any leftover documents from a previous run
    # ------------------------------------------------------------------
    step("STEP 1: Cleaning up any previous demo documents")
    deleted = collection.delete_many({"demoTag": DEMO_TAG})
    if deleted.deleted_count:
        print(f"Removed {deleted.deleted_count} leftover document(s) from a prior run.")
    else:
        print("No prior demo documents found — starting fresh.")
    time.sleep(PAUSE)

    # ------------------------------------------------------------------
    # STEP 2: Insert 3 movies  →  triggers 3 INSERT events
    # ------------------------------------------------------------------
    step("STEP 2: Inserting 3 demo movies  →  watch for INSERT events")
    movies = build_demo_movies()
    result = collection.insert_many(movies)
    ids = {m["demoMovieId"]: oid for m, oid in zip(movies, result.inserted_ids)}
    for mid, oid in ids.items():
        print(f"  Inserted {mid}  (_id: {oid})")
    time.sleep(PAUSE)

    # ------------------------------------------------------------------
    # STEP 3: Update imdb.rating  →  triggers 1 UPDATE event
    #         (visible in modes 1 and 3)
    # ------------------------------------------------------------------
    step("STEP 3: Updating imdb.rating on 'Neon Horizon'  →  watch for UPDATE event")
    collection.update_one(
        {"demoMovieId": "cs-demo-001"},
        {"$set": {"imdb.rating": 8.1, "imdb.votes": 15000}},
    )
    print("  imdb.rating  : 7.4  →  8.1")
    print("  imdb.votes   : 10 500  →  15 000")
    print("  (mode 3 WILL surface this event — it touches imdb.rating)")
    time.sleep(PAUSE)

    # ------------------------------------------------------------------
    # STEP 4: Update a non-rating field  →  triggers 1 UPDATE event
    #         (visible in mode 1, filtered out in mode 3)
    # ------------------------------------------------------------------
    step("STEP 4: Adding 'awards' field to 'The Last Cartographer'  →  UPDATE event")
    collection.update_one(
        {"demoMovieId": "cs-demo-002"},
        {"$set": {"awards": {"wins": 3, "nominations": 7}}},
    )
    print("  Added: awards.wins = 3, awards.nominations = 7")
    print("  (mode 3 will NOT surface this — imdb.rating was not touched)")
    time.sleep(PAUSE)

    # ------------------------------------------------------------------
    # STEP 5: Delete one document  →  triggers 1 DELETE event
    # ------------------------------------------------------------------
    step("STEP 5: Deleting 'Salt and Static'  →  watch for DELETE event")
    collection.delete_one({"demoMovieId": "cs-demo-003"})
    print("  Deleted cs-demo-003 ('Salt and Static')")
    time.sleep(PAUSE)

    # ------------------------------------------------------------------
    # STEP 6: Final cleanup
    # ------------------------------------------------------------------
    step("STEP 6: Final cleanup — removing remaining demo documents")
    result = collection.delete_many({"demoTag": DEMO_TAG})
    print(f"  Deleted {result.deleted_count} demo document(s)")
    print()
    print("Done. Review the watcher output in your other terminal.")
    print("Then try running with --mode 2, 3, or 4 to explore filtering and resumability.")

    client.close()


if __name__ == "__main__":
    main()
