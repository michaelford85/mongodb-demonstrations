from __future__ import annotations

import argparse
from typing import Any

from bson.binary import Binary
from pymongo.encryption import Algorithm

from common import (
    CSFLE_BACKUP_COLLECTION_NAME,
    CSFLE_COLLECTION_NAME,
    CSFLE_DB_NAME,
    CSFLE_TARGET_FIELD,
    collection_exists,
    ensure_key_vault_index,
    ensure_backup_collection,
    get_auto_encrypted_client,
    get_client_encryption,
    get_key_vault_collection,
    get_standard_client,
    load_settings,
    print_json,
    require_crypt_shared_hint,
    require_sample_data,
)


def ensure_data_key(key_vault_collection: Any, client_encryption: Any, key_alt_name: str) -> Binary:
    key = key_vault_collection.find_one({"keyAltNames": key_alt_name})
    if key:
        return key["_id"]
    return client_encryption.create_data_key("local", key_alt_names=[key_alt_name])


def build_schema_map(namespace: str, key_id: Binary) -> dict[str, Any]:
    return {
        namespace: {
            "bsonType": "object",
            "properties": {
                CSFLE_TARGET_FIELD: {
                    "encrypt": {
                        "keyId": [key_id],
                        "bsonType": "string",
                        "algorithm": Algorithm.AEAD_AES_256_CBC_HMAC_SHA_512_Deterministic,
                    }
                }
            },
        }
    }


def apply_encryption() -> None:
    settings = load_settings()
    standard_client = get_standard_client(settings)
    require_sample_data(standard_client, CSFLE_DB_NAME, CSFLE_COLLECTION_NAME)
    require_crypt_shared_hint(settings)

    ensure_key_vault_index(standard_client, settings.key_vault_namespace)
    client_encryption = get_client_encryption(settings, standard_client)
    key_vault_collection = get_key_vault_collection(standard_client, settings.key_vault_namespace)
    key_id = ensure_data_key(key_vault_collection, client_encryption, settings.csfle_key_alt_name)

    backup_count = ensure_backup_collection(
        standard_client,
        CSFLE_DB_NAME,
        CSFLE_COLLECTION_NAME,
        CSFLE_BACKUP_COLLECTION_NAME,
    )

    collection = standard_client[CSFLE_DB_NAME][CSFLE_COLLECTION_NAME]
    encrypted_count = 0

    try:
        for document in collection.find({CSFLE_TARGET_FIELD: {"$type": "string"}}):
            encrypted_value = client_encryption.encrypt(
                document[CSFLE_TARGET_FIELD],
                Algorithm.AEAD_AES_256_CBC_HMAC_SHA_512_Deterministic,
                key_alt_name=settings.csfle_key_alt_name,
            )
            collection.update_one(
                {"_id": document["_id"]},
                {"$set": {CSFLE_TARGET_FIELD: encrypted_value}},
            )
            encrypted_count += 1
    finally:
        client_encryption.close()
        standard_client.close()

    print(f"Backed up {backup_count} documents to {CSFLE_DB_NAME}.{CSFLE_BACKUP_COLLECTION_NAME}.")
    print(
        f"Encrypted {encrypted_count} {CSFLE_TARGET_FIELD} values in "
        f"{CSFLE_DB_NAME}.{CSFLE_COLLECTION_NAME}."
    )
    print("Atlas UI should now show Binary data in the email field.")


def query_encrypted(email: str | None) -> None:
    settings = load_settings()
    standard_client = get_standard_client(settings)
    require_sample_data(standard_client, CSFLE_DB_NAME, CSFLE_COLLECTION_NAME)
    require_crypt_shared_hint(settings)

    ensure_key_vault_index(standard_client, settings.key_vault_namespace)
    client_encryption = get_client_encryption(settings, standard_client)
    key_vault_collection = get_key_vault_collection(standard_client, settings.key_vault_namespace)
    key_id = ensure_data_key(key_vault_collection, client_encryption, settings.csfle_key_alt_name)
    schema_map = build_schema_map(f"{CSFLE_DB_NAME}.{CSFLE_COLLECTION_NAME}", key_id)
    encrypted_client = get_auto_encrypted_client(settings, schema_map=schema_map)

    try:
        if email is None:
            backup = standard_client[CSFLE_DB_NAME][CSFLE_BACKUP_COLLECTION_NAME].find_one(
                {CSFLE_TARGET_FIELD: {"$type": "string"}}
            )
            if not backup:
                raise RuntimeError(
                    "No plaintext backup document found. Run apply first or pass --email explicitly."
                )
            email = backup[CSFLE_TARGET_FIELD]

        decrypted_match = encrypted_client[CSFLE_DB_NAME][CSFLE_COLLECTION_NAME].find_one(
            {CSFLE_TARGET_FIELD: email},
            {"name": 1, CSFLE_TARGET_FIELD: 1},
        )
        raw_match = standard_client[CSFLE_DB_NAME][CSFLE_COLLECTION_NAME].find_one(
            {"_id": decrypted_match["_id"]} if decrypted_match else {"_id": None},
            {CSFLE_TARGET_FIELD: 1},
        )

        print(f"Querying with plaintext email: {email}")
        print_json("Encrypted client result", decrypted_match)
        print_json("Raw Atlas-stored value", raw_match)
        print(
            "If you run the same plaintext filter in Atlas without the key material, it will not match."
        )
    finally:
        encrypted_client.close()
        client_encryption.close()
        standard_client.close()


def decrypt_sample(email: str | None) -> None:
    settings = load_settings()
    standard_client = get_standard_client(settings)
    require_sample_data(standard_client, CSFLE_DB_NAME, CSFLE_COLLECTION_NAME)

    ensure_key_vault_index(standard_client, settings.key_vault_namespace)
    client_encryption = get_client_encryption(settings, standard_client)

    try:
        if email is not None:
            backup = standard_client[CSFLE_DB_NAME][CSFLE_BACKUP_COLLECTION_NAME].find_one(
                {CSFLE_TARGET_FIELD: email}
            )
            if not backup:
                raise RuntimeError(f"No backup document found for email {email}.")
            document = standard_client[CSFLE_DB_NAME][CSFLE_COLLECTION_NAME].find_one({"_id": backup["_id"]})
        else:
            document = standard_client[CSFLE_DB_NAME][CSFLE_COLLECTION_NAME].find_one(
                {CSFLE_TARGET_FIELD: {"$type": "binData"}}
            )

        if not document:
            raise RuntimeError("No encrypted document found. Run apply first.")

        encrypted_value = document[CSFLE_TARGET_FIELD]
        if not isinstance(encrypted_value, Binary):
            raise RuntimeError("Selected document is not encrypted.")

        decrypted_value = client_encryption.decrypt(encrypted_value)
        print_json("Decrypted field", {"_id": document["_id"], CSFLE_TARGET_FIELD: decrypted_value})
    finally:
        client_encryption.close()
        standard_client.close()


def remove_encryption() -> None:
    settings = load_settings()
    standard_client = get_standard_client(settings)
    require_sample_data(standard_client, CSFLE_DB_NAME, CSFLE_COLLECTION_NAME)

    ensure_key_vault_index(standard_client, settings.key_vault_namespace)
    client_encryption = get_client_encryption(settings, standard_client)
    collection = standard_client[CSFLE_DB_NAME][CSFLE_COLLECTION_NAME]
    decrypted_count = 0

    try:
        for document in collection.find({CSFLE_TARGET_FIELD: {"$type": "binData"}}):
            encrypted_value = document[CSFLE_TARGET_FIELD]
            if not isinstance(encrypted_value, Binary):
                continue
            decrypted_value = client_encryption.decrypt(encrypted_value)
            collection.update_one(
                {"_id": document["_id"]},
                {"$set": {CSFLE_TARGET_FIELD: decrypted_value}},
            )
            decrypted_count += 1
    finally:
        client_encryption.close()

    if collection_exists(standard_client, CSFLE_DB_NAME, CSFLE_BACKUP_COLLECTION_NAME):
        standard_client[CSFLE_DB_NAME][CSFLE_BACKUP_COLLECTION_NAME].drop()
    standard_client.close()

    print(
        f"Decrypted {decrypted_count} {CSFLE_TARGET_FIELD} values in "
        f"{CSFLE_DB_NAME}.{CSFLE_COLLECTION_NAME}."
    )
    print(f"Dropped backup collection {CSFLE_DB_NAME}.{CSFLE_BACKUP_COLLECTION_NAME}.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CSFLE demo for sample_mflix.users.email")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("apply", help="Encrypt sample_mflix.users.email in place.")

    query_parser = subparsers.add_parser("query", help="Query encrypted email values through an encrypted client.")
    query_parser.add_argument("--email", help="Plaintext email to query for.")

    decrypt_parser = subparsers.add_parser("decrypt", help="Decrypt one encrypted email value for inspection.")
    decrypt_parser.add_argument("--email", help="Plaintext email to inspect, matched via the backup collection.")

    subparsers.add_parser("remove", help="Decrypt email values and return the collection to plaintext.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "apply":
        apply_encryption()
    elif args.command == "query":
        query_encrypted(args.email)
    elif args.command == "decrypt":
        decrypt_sample(args.email)
    elif args.command == "remove":
        remove_encryption()


if __name__ == "__main__":
    main()
