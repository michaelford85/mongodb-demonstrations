"""Remove the collections (and their vector indexes) this demo created in Atlas.

    python scripts/cleanup.py          # list what would be dropped
    python scripts/cleanup.py --yes    # actually drop it

Only collections named <COLLECTION_PREFIX>_* in DB_NAME are touched. Dropping a
collection also removes its Atlas Search / Vector Search indexes. The local
embedding cache (.cache/) and downloaded data (data/) are separate: delete those
folders yourself if you want them gone.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
from pymongo import MongoClient  # noqa: E402

from lib.config import is_placeholder, load_settings  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="drop the listed collections")
    args = ap.parse_args()

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    settings = load_settings()
    if is_placeholder(settings.mongodb_uri):
        print("MONGODB_URI is not configured in .env.", file=sys.stderr)
        return 1
    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=15000)
    db = client[settings.db_name]
    prefix = settings.collection_prefix + "_"
    targets = sorted(c for c in db.list_collection_names() if c.startswith(prefix))
    if not targets:
        print(f"Nothing to remove: no '{prefix}*' collections in database '{settings.db_name}'.")
        return 0
    print(f"{'Dropping' if args.yes else 'Would drop'} from '{settings.db_name}':")
    for name in targets:
        print(f"  - {name}")
        if args.yes:
            db[name].drop()
    if not args.yes:
        print("Re-run with --yes to drop them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
