import os

from dotenv import load_dotenv
from pymongo import MongoClient

DEMO_TAG = "crud-flex-schema-demo-v1"


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def main():
    load_dotenv()

    uri = require_env("MONGODB_URI")
    db_name = require_env("DB_NAME")
    collection_name = require_env("COLLECTION_NAME")

    client = MongoClient(uri)
    try:
        collection = client[db_name][collection_name]
        query = {"demoTag": DEMO_TAG}
        existing_count = collection.count_documents(query)

        if existing_count == 0:
            print("No demo movies found. Nothing to delete.")
            return

        result = collection.delete_many(query)
        print(f"Deleted {result.deleted_count} demo movies from {db_name}.{collection_name}.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
