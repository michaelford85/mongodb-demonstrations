"""
Looks up a movie by title on both the live cluster and the federated endpoint
to show which storage tier the document lives on.

Usage:
    python3 title_lookup.py                  # prompts for a title
    python3 title_lookup.py "Curious George" # title passed as argument

The search is case-insensitive and matches substrings, so partial titles work.
If the movie was archived, it will not appear on the live cluster but will be
found via the federated endpoint — illustrating transparent tier routing.
"""

import os
import sys
import time
from pymongo import MongoClient
from pymongo.errors import ConfigurationError, ServerSelectionTimeoutError
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI     = os.environ["MONGODB_URI"]
FEDERATED_URI   = os.environ.get("FEDERATED_URI", "")
DB_NAME         = os.environ.get("DB_NAME", "sample_mflix")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "movies")
CUTOFF_YEAR     = int(os.environ.get("ARCHIVE_CUTOFF_YEAR", "2001"))

FIELDS = {"title": 1, "year": 1, "genres": 1, "plot": 1, "_id": 0}


def search(uri, label, title_pattern):
    print(f"\n{'='*62}")
    print(f"  {label}")
    print(f"{'='*62}\n")

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
        client.admin.command("ping")  # warm the connection
        coll = client[DB_NAME][COLLECTION_NAME]

        query = {"title": {"$regex": title_pattern, "$options": "i"}}

        start = time.time()
        docs = list(coll.find(query, FIELDS).sort("year", 1))
        elapsed_ms = (time.time() - start) * 1000

        if not docs:
            print(f"  No results found  ({elapsed_ms:.0f}ms)")
            if label.startswith("LIVE"):
                print(f"  → If you expected a result, the document may have been")
                print(f"    archived (year < {CUTOFF_YEAR}). Try the federated endpoint.")
        else:
            print(f"  {len(docs)} result(s) found  ({elapsed_ms:.0f}ms)\n")
            for doc in docs:
                year = doc.get("year", "unknown")
                tier = "cold (archived)" if isinstance(year, int) and year < CUTOFF_YEAR else \
                       "hot (live)"      if isinstance(year, int) else \
                       "cold (archived — string year)"
                print(f"  Title  : {doc.get('title')}")
                print(f"  Year   : {year}  [{tier}]")
                print(f"  Genres : {', '.join(doc.get('genres', []))}")
                plot = doc.get("plot", "")
                if plot:
                    print(f"  Plot   : {plot[:120]}{'…' if len(plot) > 120 else ''}")
                print()

        client.close()

    except ConfigurationError as e:
        print(f"  Connection error: {e}")
    except ServerSelectionTimeoutError as e:
        print(f"  Could not reach server within timeout: {e}")


def main():
    if len(sys.argv) > 1:
        title = " ".join(sys.argv[1:])
    else:
        title = input("Enter a movie title (or partial title) to look up: ").strip()

    if not title:
        print("No title provided. Exiting.")
        sys.exit(1)

    print(f"\n=== Title Lookup: \"{title}\" ===")
    print(f"Archive cutoff : year < {CUTOFF_YEAR}")
    print(f"Dataset        : {DB_NAME}.{COLLECTION_NAME}")

    search(MONGODB_URI, "LIVE CLUSTER  (hot tier — MONGODB_URI)", title)

    if FEDERATED_URI:
        search(FEDERATED_URI, "ATLAS DATA FEDERATION  (hot + cold tiers — FEDERATED_URI)", title)
        print("─" * 62)
        print("Interpretation:")
        print(f"  Found on LIVE only   → year >= {CUTOFF_YEAR}, stored on the cluster")
        print(f"  Found on FEDERATED   → may be archived (year < {CUTOFF_YEAR})")
        print(f"  Found on both        → year >= {CUTOFF_YEAR}, visible from either endpoint")
        print(f"  Missing on LIVE,")
        print(f"  present on FEDERATED → document is in cold (archived) storage")
    else:
        print("\n[FEDERATED_URI not set — skipping federated lookup]")
        print("Add FEDERATED_URI to .env using 'Connect to Cluster and Online Archive'")
        print("from Atlas UI → Online Archive → Connect.")


if __name__ == "__main__":
    main()
