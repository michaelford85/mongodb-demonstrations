"""Print the build status of the lab's search indexes.

    python scripts/status.py

Use this to confirm both indexes are `READY` before running searches.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.client import (  # noqa: E402
    get_collection, DB_NAME, COLLECTION_NAME, VECTOR_INDEX, TEXT_INDEX,
)


def main() -> None:
    coll = get_collection()
    count = coll.count_documents({})
    print(f"Namespace: {DB_NAME}.{COLLECTION_NAME}  ({count} documents)\n")

    indexes = {ix["name"]: ix for ix in coll.list_search_indexes()}
    for name in (VECTOR_INDEX, TEXT_INDEX):
        ix = indexes.get(name)
        if not ix:
            print(f"  {name:<24} MISSING — run scripts/create_indexes.py")
            continue
        status = ix.get("status", "UNKNOWN")
        queryable = ix.get("queryable", False)
        flag = "READY" if queryable else status
        print(f"  {name:<24} {flag}")

    if all(indexes.get(n, {}).get("queryable") for n in (VECTOR_INDEX, TEXT_INDEX)):
        print("\nBoth indexes are queryable. Run: streamlit run app.py")
    else:
        print("\nIndexes still building. Wait ~1-2 minutes and re-run this.")


if __name__ == "__main__":
    main()
