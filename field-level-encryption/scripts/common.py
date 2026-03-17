from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bson.codec_options import CodecOptions
from bson.json_util import dumps
from pymongo import ASCENDING, MongoClient
from pymongo.encryption import ClientEncryption
from pymongo.encryption_options import AutoEncryptionOpts
from dotenv import load_dotenv


CSFLE_DB_NAME = "sample_mflix"
CSFLE_COLLECTION_NAME = "users"
CSFLE_BACKUP_COLLECTION_NAME = "users_csfle_backup"
CSFLE_TARGET_FIELD = "email"

QE_DB_NAME = "sample_analytics"
QE_COLLECTION_NAME = "accounts"
QE_BACKUP_COLLECTION_NAME = "accounts_qe_backup"
QE_TARGET_FIELD = "limit"


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str
    key_vault_namespace: str
    local_master_key_path: Path
    crypt_shared_lib_path: str | None
    csfle_key_alt_name: str
    qe_key_alt_name: str
    qe_range_min: int
    qe_range_max: int
    qe_range_sparsity: int

    @property
    def kms_providers(self) -> dict[str, dict[str, bytes]]:
        return {"local": {"key": ensure_local_master_key(self.local_master_key_path)}}


def load_settings() -> Settings:
    load_dotenv()

    mongodb_uri = os.environ.get("MONGODB_URI")
    if not mongodb_uri:
        raise RuntimeError("MONGODB_URI is required. Copy .env.example to .env and fill it in.")

    return Settings(
        mongodb_uri=mongodb_uri,
        key_vault_namespace=os.environ.get("KEY_VAULT_NAMESPACE", "encryption.__keyVault"),
        local_master_key_path=Path(os.environ.get("LOCAL_MASTER_KEY_PATH", ".keys/local-master-key.bin")),
        crypt_shared_lib_path=os.environ.get("CRYPT_SHARED_LIB_PATH"),
        csfle_key_alt_name=os.environ.get("CSFLE_KEY_ALT_NAME", "demo-csfle-key"),
        qe_key_alt_name=os.environ.get("QE_KEY_ALT_NAME", "demo-qe-key"),
        qe_range_min=int(os.environ.get("QE_RANGE_MIN", "0")),
        qe_range_max=int(os.environ.get("QE_RANGE_MAX", "20000")),
        qe_range_sparsity=int(os.environ.get("QE_RANGE_SPARSITY", "1")),
    )


def ensure_local_master_key(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        key = secrets.token_bytes(96)
        path.write_bytes(key)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return key

    key = path.read_bytes()
    if len(key) != 96:
        raise RuntimeError(
            f"Local master key at {path} must be exactly 96 bytes, found {len(key)} bytes."
        )
    return key


def get_standard_client(settings: Settings) -> MongoClient:
    return MongoClient(settings.mongodb_uri)


def get_auto_encrypted_client(
    settings: Settings,
    *,
    schema_map: dict[str, Any] | None = None,
    encrypted_fields_map: dict[str, Any] | None = None,
    bypass_query_analysis: bool = False,
) -> MongoClient:
    kwargs: dict[str, Any] = {}
    if settings.crypt_shared_lib_path:
        kwargs["crypt_shared_lib_path"] = settings.crypt_shared_lib_path

    auto_encryption_opts = AutoEncryptionOpts(
        settings.kms_providers,
        settings.key_vault_namespace,
        schema_map=schema_map,
        encrypted_fields_map=encrypted_fields_map,
        bypass_query_analysis=bypass_query_analysis,
        **kwargs,
    )
    return MongoClient(settings.mongodb_uri, auto_encryption_opts=auto_encryption_opts)


def get_client_encryption(settings: Settings, key_vault_client: MongoClient) -> ClientEncryption:
    return ClientEncryption(
        settings.kms_providers,
        settings.key_vault_namespace,
        key_vault_client,
        CodecOptions(),
    )


def ensure_key_vault_index(client: MongoClient, key_vault_namespace: str) -> None:
    database_name, collection_name = key_vault_namespace.split(".", 1)
    client[database_name][collection_name].create_index(
        [("keyAltNames", ASCENDING)],
        unique=True,
        partialFilterExpression={"keyAltNames": {"$exists": True}},
        name="keyAltNames_1",
    )


def get_key_vault_collection(client: MongoClient, key_vault_namespace: str):
    database_name, collection_name = key_vault_namespace.split(".", 1)
    return client[database_name][collection_name]


def collection_exists(client: MongoClient, database_name: str, collection_name: str) -> bool:
    return collection_name in client[database_name].list_collection_names()


def clone_collection(
    client: MongoClient,
    database_name: str,
    source_collection_name: str,
    target_collection_name: str,
) -> int:
    database = client[database_name]
    target = database[target_collection_name]
    if target_collection_name in database.list_collection_names():
        target.drop()
    documents = list(database[source_collection_name].find({}))
    if documents:
        target.insert_many(documents)
    return len(documents)


def ensure_backup_collection(
    client: MongoClient,
    database_name: str,
    source_collection_name: str,
    backup_collection_name: str,
) -> int:
    database = client[database_name]
    if backup_collection_name in database.list_collection_names():
        return database[backup_collection_name].count_documents({})
    return clone_collection(client, database_name, source_collection_name, backup_collection_name)


def print_json(label: str, payload: Any) -> None:
    print(f"{label}:")
    print(dumps(payload, indent=2, sort_keys=True))


def require_sample_data(client: MongoClient, database_name: str, collection_name: str) -> None:
    if not collection_exists(client, database_name, collection_name):
        raise RuntimeError(
            f"Expected sample collection {database_name}.{collection_name} to exist in Atlas."
        )


def require_crypt_shared_hint(settings: Settings) -> None:
    if settings.crypt_shared_lib_path:
        return
    print(
        "Note: if automatic encryption fails because the Automatic Encryption Shared Library "
        "cannot be found, set CRYPT_SHARED_LIB_PATH in .env."
    )
