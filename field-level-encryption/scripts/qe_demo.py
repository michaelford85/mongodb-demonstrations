from __future__ import annotations

import argparse
from typing import Any

from common import (
    QE_BACKUP_COLLECTION_NAME,
    QE_COLLECTION_NAME,
    QE_DB_NAME,
    QE_TARGET_FIELD,
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


def ensure_data_key(key_vault_collection: Any, client_encryption: Any, key_alt_name: str) -> Any:
    key = key_vault_collection.find_one({"keyAltNames": key_alt_name})
    if key:
        return key["_id"]
    return client_encryption.create_data_key("local", key_alt_names=[key_alt_name])


def build_encrypted_fields(settings: Any, key_id: Any) -> dict[str, Any]:
    return {
        "fields": [
            {
                "path": QE_TARGET_FIELD,
                "keyId": key_id,
                "bsonType": "int",
                "queries": {
                    "queryType": "range",
                    "min": settings.qe_range_min,
                    "max": settings.qe_range_max,
                    "sparsity": settings.qe_range_sparsity,
                },
            }
        ]
    }


def ensure_plaintext_backup(standard_client: Any) -> int:
    return ensure_backup_collection(
        standard_client,
        QE_DB_NAME,
        QE_COLLECTION_NAME,
        QE_BACKUP_COLLECTION_NAME,
    )


def apply_encryption() -> None:
    settings = load_settings()
    standard_client = get_standard_client(settings)
    require_sample_data(standard_client, QE_DB_NAME, QE_COLLECTION_NAME)
    require_crypt_shared_hint(settings)

    ensure_key_vault_index(standard_client, settings.key_vault_namespace)
    backup_count = ensure_plaintext_backup(standard_client)

    client_encryption = get_client_encryption(settings, standard_client)
    key_vault_collection = get_key_vault_collection(standard_client, settings.key_vault_namespace)
    key_id = ensure_data_key(key_vault_collection, client_encryption, settings.qe_key_alt_name)
    encrypted_fields = build_encrypted_fields(settings, key_id)
    encrypted_client = get_auto_encrypted_client(
        settings,
        encrypted_fields_map={f"{QE_DB_NAME}.{QE_COLLECTION_NAME}": encrypted_fields},
    )
    inserted_count = 0
    encrypted_fields_with_ids = encrypted_fields

    try:
        if collection_exists(standard_client, QE_DB_NAME, QE_COLLECTION_NAME):
            standard_client[QE_DB_NAME][QE_COLLECTION_NAME].drop()

        _, encrypted_fields_with_ids = client_encryption.create_encrypted_collection(
            encrypted_client[QE_DB_NAME],
            QE_COLLECTION_NAME,
            encrypted_fields,
            "local",
        )

        source_documents = standard_client[QE_DB_NAME][QE_BACKUP_COLLECTION_NAME].find({})
        for document in source_documents:
            encrypted_client[QE_DB_NAME][QE_COLLECTION_NAME].insert_one(document)
            inserted_count += 1
    finally:
        client_encryption.close()
        encrypted_client.close()
        standard_client.close()

    print(f"Backed up {backup_count} documents to {QE_DB_NAME}.{QE_BACKUP_COLLECTION_NAME}.")
    print(
        f"Created Queryable Encryption collection {QE_DB_NAME}.{QE_COLLECTION_NAME} "
        f"and reinserted {inserted_count} documents."
    )
    print_json("Encrypted fields configuration", encrypted_fields_with_ids)
    print("Atlas UI should now show encrypted limit values and enxcol.* metadata collections.")


def range_query(min_value: int, max_value: int) -> None:
    settings = load_settings()
    standard_client = get_standard_client(settings)
    require_sample_data(standard_client, QE_DB_NAME, QE_COLLECTION_NAME)
    require_crypt_shared_hint(settings)

    key_vault_collection = get_key_vault_collection(standard_client, settings.key_vault_namespace)
    client_encryption = get_client_encryption(settings, standard_client)
    key_id = ensure_data_key(key_vault_collection, client_encryption, settings.qe_key_alt_name)
    encrypted_fields = build_encrypted_fields(settings, key_id)
    encrypted_client = get_auto_encrypted_client(
        settings,
        encrypted_fields_map={f"{QE_DB_NAME}.{QE_COLLECTION_NAME}": encrypted_fields},
    )

    try:
        matches = list(
            encrypted_client[QE_DB_NAME][QE_COLLECTION_NAME]
            .find({QE_TARGET_FIELD: {"$gt": min_value, "$lt": max_value}}, {"account_id": 1, QE_TARGET_FIELD: 1})
            .limit(5)
        )
        raw_match = None
        if matches:
            raw_match = standard_client[QE_DB_NAME][QE_COLLECTION_NAME].find_one(
                {"_id": matches[0]["_id"]},
                {"account_id": 1, QE_TARGET_FIELD: 1, "__safeContent__": 1},
            )

        print(f"Range query: {QE_TARGET_FIELD} > {min_value} and < {max_value}")
        print_json("Encrypted client matches", matches)
        print_json("Raw Atlas-stored document", raw_match)
        print(
            "The raw ciphertext for equal plaintext values is randomized, but the encrypted client "
            "can still satisfy the range predicate."
        )
    finally:
        client_encryption.close()
        encrypted_client.close()
        standard_client.close()


def decrypt_sample() -> None:
    settings = load_settings()
    standard_client = get_standard_client(settings)
    require_sample_data(standard_client, QE_DB_NAME, QE_COLLECTION_NAME)
    require_crypt_shared_hint(settings)

    key_vault_collection = get_key_vault_collection(standard_client, settings.key_vault_namespace)
    client_encryption = get_client_encryption(settings, standard_client)
    key_id = ensure_data_key(key_vault_collection, client_encryption, settings.qe_key_alt_name)
    encrypted_fields = build_encrypted_fields(settings, key_id)
    encrypted_client = get_auto_encrypted_client(
        settings,
        encrypted_fields_map={f"{QE_DB_NAME}.{QE_COLLECTION_NAME}": encrypted_fields},
    )

    try:
        document = encrypted_client[QE_DB_NAME][QE_COLLECTION_NAME].find_one(
            {},
            {"account_id": 1, QE_TARGET_FIELD: 1},
        )
        raw_document = None
        if document:
            raw_document = standard_client[QE_DB_NAME][QE_COLLECTION_NAME].find_one(
                {"_id": document["_id"]},
                {"account_id": 1, QE_TARGET_FIELD: 1, "__safeContent__": 1},
            )

        print_json("Decrypted field", document)
        print_json("Raw Atlas-stored document", raw_document)
    finally:
        client_encryption.close()
        encrypted_client.close()
        standard_client.close()


def remove_encryption() -> None:
    settings = load_settings()
    standard_client = get_standard_client(settings)
    require_sample_data(standard_client, QE_DB_NAME, QE_COLLECTION_NAME)
    require_crypt_shared_hint(settings)

    key_vault_collection = get_key_vault_collection(standard_client, settings.key_vault_namespace)
    client_encryption = get_client_encryption(settings, standard_client)
    key_id = ensure_data_key(key_vault_collection, client_encryption, settings.qe_key_alt_name)
    encrypted_fields = build_encrypted_fields(settings, key_id)
    encrypted_client = get_auto_encrypted_client(
        settings,
        encrypted_fields_map={f"{QE_DB_NAME}.{QE_COLLECTION_NAME}": encrypted_fields},
    )
    plaintext_documents = []

    try:
        plaintext_documents = list(encrypted_client[QE_DB_NAME][QE_COLLECTION_NAME].find({}))
        encrypted_client[QE_DB_NAME].drop_collection(QE_COLLECTION_NAME)
        if plaintext_documents:
            standard_client[QE_DB_NAME][QE_COLLECTION_NAME].insert_many(plaintext_documents)
    finally:
        client_encryption.close()
        encrypted_client.close()
        standard_client.close()

    restored_client = get_standard_client(settings)
    if collection_exists(restored_client, QE_DB_NAME, QE_BACKUP_COLLECTION_NAME):
        restored_client[QE_DB_NAME][QE_BACKUP_COLLECTION_NAME].drop()
    restored_client.close()

    print(
        f"Restored {len(plaintext_documents)} plaintext documents to {QE_DB_NAME}.{QE_COLLECTION_NAME}."
    )
    print(f"Dropped backup collection {QE_DB_NAME}.{QE_BACKUP_COLLECTION_NAME}.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Queryable Encryption demo for sample_analytics.accounts.limit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("apply", help="Recreate sample_analytics.accounts as a QE-enabled collection.")

    query_parser = subparsers.add_parser("query", help="Run a range query through an encrypted client.")
    query_parser.add_argument("--min", dest="min_value", type=int, default=5000, help="Lower bound (exclusive).")
    query_parser.add_argument("--max", dest="max_value", type=int, default=10000, help="Upper bound (exclusive).")

    subparsers.add_parser("decrypt", help="Read one document back through the encrypted client.")
    subparsers.add_parser("remove", help="Drop the QE collection and restore plaintext documents.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "apply":
        apply_encryption()
    elif args.command == "query":
        range_query(args.min_value, args.max_value)
    elif args.command == "decrypt":
        decrypt_sample()
    elif args.command == "remove":
        remove_encryption()


if __name__ == "__main__":
    main()
