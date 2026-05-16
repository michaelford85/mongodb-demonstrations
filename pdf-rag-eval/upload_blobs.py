"""Upload the synthesized PDFs to Azure Blob Storage.

Reads data/pdf_manifest.jsonl (produced by generate_pdfs.py), uploads
each PDF to the configured container, and rewrites the manifest in
place with the resulting blob URL alongside the existing metadata.
Subsequent steps (embed_and_load.py, retrieve.py) read the manifest
and persist blob_path / blob_url into every chunk document on both
backends.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from azure.storage.blob import BlobServiceClient, ContentSettings

from config import DATA_DIR, SOURCE_PDF_DIR, load_settings

MANIFEST = DATA_DIR / "pdf_manifest.jsonl"


def _read_manifest(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(
            f"No manifest at {path}. Run generate_pdfs.py first."
        )
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _write_manifest(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_PDF_DIR)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite blobs that already exist at the target path.",
    )
    args = parser.parse_args()

    records = _read_manifest(args.manifest)

    svc = BlobServiceClient.from_connection_string(
        settings.azure_storage_connection_string
    )
    container = svc.get_container_client(settings.azure_storage_container)
    # The Terraform creates the container, but recreate idempotently in
    # case someone deleted it manually.
    try:
        container.create_container()
    except Exception:
        pass

    pdf_ct = ContentSettings(content_type="application/pdf")
    updated: list[dict] = []
    for rec in records:
        local = args.source_dir / rec["filename"]
        if not local.exists():
            raise SystemExit(
                f"Manifest references {local} but the file is missing. "
                "Re-run generate_pdfs.py."
            )
        blob_path = f"catalog/{rec['filename']}"
        blob = container.get_blob_client(blob_path)
        with local.open("rb") as fh:
            blob.upload_blob(
                fh,
                overwrite=args.overwrite,
                content_settings=pdf_ct,
                metadata={
                    "document_id": rec["document_id"],
                    "category": rec["category"],
                    "item_id": rec["item_id"],
                    "vendor": rec["vendor"],
                    "revision": rec["revision"],
                },
            )
        rec["blob_path"] = blob_path
        rec["blob_url"] = blob.url
        updated.append(rec)
        print(f"  uploaded {blob_path}")

    _write_manifest(args.manifest, updated)
    print(
        f"Uploaded {len(updated)} PDFs to "
        f"{settings.azure_storage_container} in account "
        f"{svc.account_name}. Manifest updated at {args.manifest}."
    )


if __name__ == "__main__":
    main()
