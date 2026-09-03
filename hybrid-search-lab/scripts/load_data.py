"""Load movie data into the lab collection.

Three sources, in order of convenience:
  * the curated, self-contained set in data/movies.json (default), whose plots
    are written so keyword search misses intent-based queries while semantic /
    hybrid search find them;
  * any JSON array of movies you point --file at;
  * N random REAL movies copied from an Atlas sample dataset via --sample
    (defaults to the built-in sample_mflix.movies).

    python scripts/load_data.py                          # insert curated set (skips if present)
    python scripts/load_data.py --drop                   # wipe and reload from scratch
    python scripts/load_data.py --file my.json --append  # add your own movies
    python scripts/load_data.py --sample 200 --drop      # load 200 real movies (sample_mflix)
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.client import get_collection, get_client, DB_NAME, COLLECTION_NAME  # noqa: E402

DATA_FILE = Path(__file__).parent.parent / "data" / "movies.json"
DEFAULT_SOURCE = "sample_mflix.movies"

# Only the fields the lab searches / displays — keeps the docs small and matches
# the curated schema so every strategy behaves the same regardless of source.
_PROJECT = {"_id": 0, "title": 1, "year": 1, "genres": 1, "plot": 1}


def _sample_real_movies(n: int, source: str) -> list:
    """Copy N random real movies (that have a plot) from an Atlas sample namespace.

    Uses a $sample aggregation, so it is pure MongoDB — the same query you could
    run in mongosh. Requires the sample dataset to be loaded on the cluster.
    """
    db_name, _, coll_name = source.partition(".")
    if not coll_name:
        raise SystemExit(f"--source must be 'db.collection', got: {source!r}")
    src = get_client()[db_name][coll_name]
    if src.estimated_document_count() == 0:
        raise SystemExit(
            f"Source namespace '{source}' is empty or missing.\n"
            f"Load it once from the Atlas UI (your cluster -> ... -> Load Sample "
            f"Dataset, which adds sample_mflix), or use --file for your own JSON."
        )
    pipeline = [
        {"$match": {"plot": {"$type": "string", "$ne": ""},
                    "title": {"$type": "string"}}},
        {"$sample": {"size": n}},
        {"$project": _PROJECT},
    ]
    return list(src.aggregate(pipeline))


def main() -> None:
    parser = argparse.ArgumentParser(description="Load lab movie data.")
    parser.add_argument("--drop", action="store_true",
                        help="drop the collection before loading")
    parser.add_argument("--file", default=str(DATA_FILE),
                        help="path to a JSON array of movies to load "
                             "(default: the curated data/movies.json)")
    parser.add_argument("--sample", type=int, metavar="N",
                        help="instead of a file, copy N random real movies "
                             "(that have a plot) from an Atlas sample dataset")
    parser.add_argument("--source", default=DEFAULT_SOURCE,
                        help=f"source namespace for --sample "
                             f"(default: {DEFAULT_SOURCE})")
    parser.add_argument("--append", action="store_true",
                        help="insert even if the collection already has documents")
    args = parser.parse_args()

    coll = get_collection()

    if args.drop:
        coll.drop()
        print(f"Dropped {DB_NAME}.{COLLECTION_NAME}")

    existing = coll.count_documents({})
    if existing and not args.drop and not args.append:
        print(f"{existing} documents already present in {DB_NAME}.{COLLECTION_NAME}. "
              f"Use --drop to reload, or --append to add more.")
        return

    if args.sample:
        movies = _sample_real_movies(args.sample, args.source)
        origin = f"{args.source} (random sample)"
        if not movies:
            print(f"No movies with a plot found in {args.source}.")
            return
    else:
        data_file = Path(args.file)
        movies = json.loads(data_file.read_text())
        origin = data_file.name

    result = coll.insert_many(movies)
    print(f"Inserted {len(result.inserted_ids)} movies from {origin} into "
          f"{DB_NAME}.{COLLECTION_NAME}")
    print("Atlas Automated Embedding indexes new plots automatically once the "
          "vector index exists — there is no separate re-embedding step. If you "
          "have not created the indexes yet, run: python scripts/create_indexes.py")


if __name__ == "__main__":
    main()
