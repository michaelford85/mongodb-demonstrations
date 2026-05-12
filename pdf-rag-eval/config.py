"""Shared configuration for the pdf-rag-eval demo.

Loads from .env via python-dotenv and validates the values used by every
script in this folder. Designed to fail fast with a clear error if any
required variable is missing or malformed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
SOURCE_PDF_DIR = DATA_DIR / "source_pdfs"
CHUNKS_FILE = DATA_DIR / "chunks.jsonl"

_ALLOWED_EMBED_DIMS = (256, 512, 1024, 2048)


@dataclass(frozen=True)
class Settings:
    # Voyage
    voyage_api_key: str
    voyage_model: str
    embed_dim: int

    # Cosmos
    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database: str
    cosmos_container: str
    cosmos_vector_path: str
    cosmos_partition_key_path: str

    # MongoDB Atlas
    mongo_uri: str
    mongo_db: str
    mongo_collection: str
    atlas_vector_index: str

    # Azure Blob
    azure_storage_connection_string: str
    azure_storage_container: str

    # Generation / chunking
    pdf_count: int
    chunk_char_size: int
    chunk_char_overlap: int


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Environment variable {name} is not set. "
            "Copy .env.example to .env and fill it in."
        )
    return value


def load_settings() -> Settings:
    embed_dim = int(os.getenv("EMBED_DIM", "1024"))
    if embed_dim not in _ALLOWED_EMBED_DIMS:
        raise ValueError(f"EMBED_DIM must be one of {_ALLOWED_EMBED_DIMS}.")

    pdf_count = int(os.getenv("PDF_COUNT", "20"))
    if not 1 <= pdf_count <= 200:
        raise ValueError("PDF_COUNT must be between 1 and 200.")

    chunk_char_size = int(os.getenv("CHUNK_CHAR_SIZE", "1500"))
    chunk_char_overlap = int(os.getenv("CHUNK_CHAR_OVERLAP", "200"))
    if chunk_char_overlap >= chunk_char_size:
        raise ValueError("CHUNK_CHAR_OVERLAP must be smaller than CHUNK_CHAR_SIZE.")

    return Settings(
        voyage_api_key=_require("VOYAGE_API_KEY"),
        voyage_model=os.getenv("VOYAGE_MODEL", "voyage-4-large"),
        embed_dim=embed_dim,
        cosmos_endpoint=_require("COSMOS_ENDPOINT"),
        cosmos_key=_require("COSMOS_KEY"),
        cosmos_database=os.getenv("COSMOS_DATABASE", "ragdb"),
        cosmos_container=os.getenv("COSMOS_CONTAINER", "chunks"),
        cosmos_vector_path=os.getenv("COSMOS_VECTOR_PATH", "/embedding"),
        cosmos_partition_key_path=os.getenv(
            "COSMOS_PARTITION_KEY_PATH", "/document_id"
        ),
        mongo_uri=_require("MONGODB_URI"),
        mongo_db=os.getenv("MONGO_DB", "pdf_rag_eval"),
        mongo_collection=os.getenv("MONGO_COLLECTION", "chunks"),
        atlas_vector_index=os.getenv("ATLAS_VECTOR_INDEX", "chunks_vector_idx"),
        azure_storage_connection_string=_require("AZURE_STORAGE_CONNECTION_STRING"),
        azure_storage_container=os.getenv("AZURE_STORAGE_CONTAINER", "pdfs"),
        pdf_count=pdf_count,
        chunk_char_size=chunk_char_size,
        chunk_char_overlap=chunk_char_overlap,
    )
