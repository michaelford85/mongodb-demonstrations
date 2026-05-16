"""Extract text from the local PDFs, chunk it, embed each chunk with
Voyage AI, and write the result to data/chunks.jsonl.

Once chunks.jsonl exists, the two ingest scripts (cosmos/ingest.py and
mongodb/ingest.py) bulk-load it into their respective stores. Splitting
embedding from loading lets us pay for Voyage credits exactly once and
then re-load either backend without re-embedding.

The chunk schema is identical for both stores so the comparison demos
in 2c can score the same pairs on each side.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pypdf import PdfReader

from config import (
    CHUNKS_FILE,
    DATA_DIR,
    SOURCE_PDF_DIR,
    load_settings,
)
from embeddings import embed_chunks

MANIFEST = DATA_DIR / "pdf_manifest.jsonl"


def _read_manifest(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(
            f"No manifest at {path}. Run generate_pdfs.py and "
            "upload_blobs.py first."
        )
    with path.open("r", encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]
    missing_blob = [r for r in records if "blob_url" not in r]
    if missing_blob:
        raise SystemExit(
            f"{len(missing_blob)} manifest entries are missing blob_url; "
            "run upload_blobs.py before embedding so chunks can record "
            "the source pointer."
        )
    return records


def _extract_pages(pdf_path: Path) -> list[str]:
    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]


def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Character-window chunker with overlap.

    Simple, dependency-free, and good enough for a demo. Sentence-aware
    chunkers are a marginal recall improvement that aren't worth the
    extra dependency at this scale.
    """
    text = " ".join(text.split())
    if not text:
        return []
    if len(text) <= size:
        return [text]
    step = size - overlap
    chunks: list[str] = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + size])
        i += step
    return chunks


def _build_chunk_records(
    manifest: list[dict], source_dir: Path, size: int, overlap: int
) -> list[dict]:
    records: list[dict] = []
    for entry in manifest:
        local = source_dir / entry["filename"]
        if not local.exists():
            raise SystemExit(
                f"Manifest references {local} but the file is missing."
            )
        for page_idx, page_text in enumerate(_extract_pages(local), start=1):
            for chunk_idx, chunk_text in enumerate(
                _chunk_text(page_text, size, overlap)
            ):
                # Underscore separators because Cosmos rejects '/', '\', '?', '#'
                # in the document id field.
                chunk_id = f"{entry['document_id']}_p{page_idx:03d}_c{chunk_idx:03d}"
                records.append(
                    {
                        "chunk_id": chunk_id,
                        "document_id": entry["document_id"],
                        "blob_path": entry["blob_path"],
                        "blob_url": entry["blob_url"],
                        "filename": entry["filename"],
                        "title": entry["title"],
                        "vendor": entry["vendor"],
                        "category": entry["category"],
                        "item_id": entry["item_id"],
                        "revision": entry["revision"],
                        "page_number": page_idx,
                        "chunk_index": chunk_idx,
                        "text": chunk_text,
                    }
                )
    return records


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_PDF_DIR)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--out", type=Path, default=CHUNKS_FILE)
    parser.add_argument(
        "--size", type=int, default=settings.chunk_char_size,
        help="Characters per chunk (default from CHUNK_CHAR_SIZE).",
    )
    parser.add_argument(
        "--overlap", type=int, default=settings.chunk_char_overlap,
        help="Character overlap between chunks (default from CHUNK_CHAR_OVERLAP).",
    )
    args = parser.parse_args()

    manifest = _read_manifest(args.manifest)
    chunks = _build_chunk_records(manifest, args.source_dir, args.size, args.overlap)
    if not chunks:
        raise SystemExit("No chunks produced; check that the PDFs have extractable text.")
    print(
        f"Extracted {len(chunks)} chunks from {len(manifest)} PDFs "
        f"(size={args.size}, overlap={args.overlap}). Embedding with "
        f"{settings.voyage_model} at {settings.embed_dim} dims..."
    )

    vectors = embed_chunks(
        [c["text"] for c in chunks],
        settings.voyage_api_key,
        settings.voyage_model,
        settings.embed_dim,
    )
    if len(vectors) != len(chunks):
        raise RuntimeError(
            f"Voyage returned {len(vectors)} vectors for {len(chunks)} chunks."
        )
    for chunk, vec in zip(chunks, vectors):
        chunk["embedding"] = vec

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk) + "\n")
    print(f"Wrote {len(chunks)} embedded chunks to {args.out}.")
    print(
        "Next:\n"
        "  python -m cosmos.ingest\n"
        "  python -m mongodb.ingest --drop\n"
        "  python -m mongodb.create_index --wait"
    )


if __name__ == "__main__":
    main()
