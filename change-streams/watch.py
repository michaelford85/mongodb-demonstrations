import argparse
import json
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

RESUME_TOKEN_FILE = ".resume_token"


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def format_event(event: dict) -> str:
    op = event.get("operationType", "unknown")
    ns = event.get("ns", {})
    doc_key = event.get("documentKey", {}).get("_id", "?")

    lines = [
        "",
        "--- Change Event " + "-" * 42,
        f"  Operation  : {op.upper()}",
        f"  Namespace  : {ns.get('db', '?')}.{ns.get('coll', '?')}",
        f"  DocumentId : {doc_key}",
    ]

    if op == "insert":
        doc = event.get("fullDocument", {})
        lines.append(f"  Title      : {doc.get('title', '(no title)')}")
        lines.append(f"  Year       : {doc.get('year', '?')}")
        imdb = doc.get("imdb", {})
        lines.append(f"  IMDB       : {imdb.get('rating', '?')} ({imdb.get('votes', '?')} votes)")

    elif op == "update":
        update_desc = event.get("updateDescription", {})
        updated = update_desc.get("updatedFields", {})
        removed = update_desc.get("removedFields", [])
        if updated:
            lines.append(f"  Updated    : {json.dumps(updated, default=str)}")
        if removed:
            lines.append(f"  Removed    : {removed}")
        full_doc = event.get("fullDocument")
        if full_doc:
            imdb = full_doc.get("imdb", {})
            lines.append(
                f"  Full Doc   : '{full_doc.get('title', '?')}' "
                f"(rating now: {imdb.get('rating', '?')})"
            )

    elif op == "replace":
        full_doc = event.get("fullDocument", {})
        lines.append(f"  Replaced   : '{full_doc.get('title', '?')}'")

    elif op == "delete":
        lines.append("  (document has been removed from the collection)")

    resume_token = event.get("_id", {}).get("_data", "")
    lines.append(f"  Token      : {resume_token[:24]}...")
    return "\n".join(lines)


def save_resume_token(token: dict) -> None:
    with open(RESUME_TOKEN_FILE, "w") as f:
        json.dump(token, f)


def load_resume_token() -> dict | None:
    path = Path(RESUME_TOKEN_FILE)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def watch_mode_1(collection) -> None:
    """Watch ALL change types on the collection."""
    print()
    print("Mode 1: Watching ALL changes (insert, update, delete, replace)")
    print("  Pipeline : none — every event is delivered")
    print("  Tip      : run generate_changes.py in another terminal")
    print("  Stop     : Ctrl+C")
    print()

    with collection.watch(full_document="updateLookup") as stream:
        for event in stream:
            save_resume_token(event["_id"])
            print(format_event(event))


def watch_mode_2(collection) -> None:
    """Watch ONLY insert operations."""
    print()
    print("Mode 2: Watching INSERT operations only")
    print("  Pipeline : $match { operationType: 'insert' }")
    print("  Tip      : updates and deletes will be silently filtered out")
    print("  Stop     : Ctrl+C")
    print()

    pipeline = [{"$match": {"operationType": "insert"}}]
    with collection.watch(pipeline, full_document="updateLookup") as stream:
        for event in stream:
            save_resume_token(event["_id"])
            print(format_event(event))


def watch_mode_3(collection) -> None:
    """Watch inserts AND updates that touch the imdb.rating field."""
    print()
    print("Mode 3: Watching inserts + updates that modify 'imdb.rating'")
    print("  Pipeline : $match on operationType + updatedFields key")
    print("  Tip      : the 'awards' update in generate_changes.py will be filtered out")
    print("  Stop     : Ctrl+C")
    print()

    pipeline = [
        {
            "$match": {
                "$or": [
                    {"operationType": "insert"},
                    {
                        "operationType": "update",
                        "updateDescription.updatedFields.imdb.rating": {"$exists": True},
                    },
                ]
            }
        }
    ]
    with collection.watch(pipeline, full_document="updateLookup") as stream:
        for event in stream:
            save_resume_token(event["_id"])
            print(format_event(event))


def watch_mode_4(collection) -> None:
    """Resume the stream from the last saved resume token."""
    token = load_resume_token()
    if not token:
        print(f"\nNo resume token found at '{RESUME_TOKEN_FILE}'.")
        print("Run mode 1, 2, or 3 first to generate a token, then re-run generate_changes.py.")
        return

    print()
    print("Mode 4: Resuming from saved resume token")
    print(f"  Token file : {RESUME_TOKEN_FILE}")
    print(f"  Token      : {token.get('_data', '')[:32]}...")
    print("  Tip        : any events that occurred after this token will be replayed")
    print("  Stop       : Ctrl+C")
    print()

    with collection.watch(resume_after=token, full_document="updateLookup") as stream:
        for event in stream:
            save_resume_token(event["_id"])
            print(format_event(event))


MODES = {
    1: watch_mode_1,
    2: watch_mode_2,
    3: watch_mode_3,
    4: watch_mode_4,
}


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="MongoDB Change Streams watcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Modes:\n"
            "  1  Watch all changes (default)\n"
            "  2  Watch inserts only\n"
            "  3  Watch inserts + imdb.rating updates\n"
            "  4  Resume from last saved token\n"
        ),
    )
    parser.add_argument(
        "--mode",
        type=int,
        choices=[1, 2, 3, 4],
        default=1,
        metavar="MODE",
        help="Watch mode 1-4 (default: 1)",
    )
    args = parser.parse_args()

    uri = require_env("MONGODB_URI")
    db_name = require_env("DB_NAME")
    collection_name = require_env("COLLECTION_NAME")

    client = MongoClient(uri)
    collection = client[db_name][collection_name]

    print(f"Connected to {db_name}.{collection_name}")

    def handle_sigint(sig, frame):
        print("\n\nWatcher stopped.")
        client.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        MODES[args.mode](collection)
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
