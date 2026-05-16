"""End-to-end metadata-driven retrieval against MongoDB Atlas.

Pipeline:
    user query
      -> Voyage AI embedding (input_type='query')
      -> Atlas $vectorSearch over the chunk collection
      -> resolve blob_path / page_number from the returned chunk metadata
      -> mint a short-lived SAS URL for the source PDF in Azure Blob
      -> optionally extract just the matching page and save it locally

This is the "MongoDB metadata as the directory of your unstructured data"
story: the chunk's vector lives in Atlas, but the authoritative source
artifact stays in Blob and is fetched on demand via a signed, expiring
URL rather than being duplicated into the database.

Usage:
    python retrieve.py "what are the safety procedures" --k 5
    python retrieve.py "flammable solvent handling" --category compliance --save-pages out/
"""
from __future__ import annotations

import argparse
import datetime
import io
from pathlib import Path

from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    generate_blob_sas,
)
from pymongo import MongoClient
from pypdf import PdfReader, PdfWriter

from config import Settings, load_settings
from embeddings import embed_query


def _parse_account_key(connection_string: str) -> str:
    parts = dict(
        kv.split("=", 1) for kv in connection_string.split(";") if "=" in kv
    )
    key = parts.get("AccountKey")
    if not key:
        raise RuntimeError(
            "AccountKey not present in AZURE_STORAGE_CONNECTION_STRING."
        )
    return key


def _vector_search(
    coll, index_name: str, vector: list[float], k: int, category: str | None
) -> list[dict]:
    stage: dict = {
        "$vectorSearch": {
            "index": index_name,
            "path": "embedding",
            "queryVector": vector,
            "numCandidates": max(k * 20, 100),
            "limit": k,
        }
    }
    if category:
        stage["$vectorSearch"]["filter"] = {"category": {"$eq": category}}

    pipeline = [
        stage,
        {
            "$project": {
                "_id": 1,
                "document_id": 1,
                "blob_path": 1,
                "filename": 1,
                "title": 1,
                "vendor": 1,
                "category": 1,
                "item_id": 1,
                "page_number": 1,
                "chunk_index": 1,
                "text": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    return list(coll.aggregate(pipeline))


def _sas_url(
    account_name: str,
    account_key: str,
    container: str,
    blob_path: str,
    minutes: int,
) -> str:
    expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=minutes
    )
    token = generate_blob_sas(
        account_name=account_name,
        account_key=account_key,
        container_name=container,
        blob_name=blob_path,
        permission=BlobSasPermissions(read=True),
        expiry=expiry,
    )
    return (
        f"https://{account_name}.blob.core.windows.net/"
        f"{container}/{blob_path}?{token}"
    )


def _extract_page(blob_client, page_number: int) -> bytes:
    """Download the source PDF, slice out one page, return the page-only bytes."""
    full = blob_client.download_blob().readall()
    reader = PdfReader(io.BytesIO(full))
    if not 1 <= page_number <= len(reader.pages):
        raise ValueError(
            f"page_number={page_number} out of range for {len(reader.pages)}-page PDF."
        )
    writer = PdfWriter()
    writer.add_page(reader.pages[page_number - 1])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _snippet(text: str, width: int = 160) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 1] + "\u2026"


def _run(settings: Settings, args: argparse.Namespace) -> None:
    print(f"Embedding query with {settings.voyage_model} ({settings.embed_dim}d)...")
    qvec = embed_query(
        args.query, settings.voyage_api_key, settings.voyage_model, settings.embed_dim
    )

    client = MongoClient(settings.mongo_uri)
    coll = client[settings.mongo_db][settings.mongo_collection]
    hits = _vector_search(
        coll, settings.atlas_vector_index, qvec, args.k, args.category
    )
    if not hits:
        print("No vector-search hits. Is the Atlas index queryable yet?")
        return

    svc = BlobServiceClient.from_connection_string(
        settings.azure_storage_connection_string
    )
    account_key = _parse_account_key(settings.azure_storage_connection_string)
    container = settings.azure_storage_container
    save_dir: Path | None = args.save_pages
    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)

    for rank, hit in enumerate(hits, start=1):
        print()
        print(
            f"#{rank}  score={hit['score']:.4f}  "
            f"{hit['title']} (p.{hit['page_number']}, "
            f"cat={hit['category']}, item={hit['item_id']}, "
            f"vendor={hit['vendor']})"
        )
        print(f"      chunk_id: {hit['_id']}")
        print(f"      snippet : {_snippet(hit['text'])}")
        url = _sas_url(
            svc.account_name, account_key, container, hit["blob_path"], args.expiry
        )
        print(f"      sas url : {url}")

        if save_dir is not None:
            blob = svc.get_blob_client(container=container, blob=hit["blob_path"])
            page_bytes = _extract_page(blob, hit["page_number"])
            out_path = save_dir / (
                f"{rank:02d}-{Path(hit['filename']).stem}-p{hit['page_number']:03d}.pdf"
            )
            out_path.write_bytes(page_bytes)
            print(f"      saved   : {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Natural-language query to embed and search.")
    parser.add_argument("--k", type=int, default=5, help="Top-K to return.")
    parser.add_argument(
        "--category",
        help="Optional category filter pushed into the $vectorSearch stage "
        "(e.g. 'storage-hardware', 'industrial-supplies', 'compliance', "
        "'electronics-components'). Applied as a pre-filter, not a post-filter.",
    )
    parser.add_argument(
        "--expiry",
        type=int,
        default=15,
        help="SAS URL lifetime in minutes (default 15).",
    )
    parser.add_argument(
        "--save-pages",
        type=Path,
        default=None,
        help="If set, download each hit's source PDF and save just the "
        "matching page into this directory.",
    )
    args = parser.parse_args()
    _run(load_settings(), args)


if __name__ == "__main__":
    main()
