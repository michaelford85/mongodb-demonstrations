"""Client-side embeddings.

Two backends behind one interface:

  * Voyage AI — real embeddings for meaningful semantic search.
  * fake      — deterministic, offline unit vectors derived from a hash of the
                text. No API key, no network, no cost. Recall is meaningless,
                but the index topology, routing, and latencies are real — which
                is exactly what the scale profile needs to demonstrate.

Both produce EMBEDDING_DIM-length lists, so the flat index and the HNSW view
indexes accept either interchangeably.
"""
import hashlib
import math
import struct
import time

from .client import get_voyage, VOYAGE_MODEL, EMBEDDING_DIM


def _normalise(vec: list) -> list:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def fake_embedding(text: str, dim: int = EMBEDDING_DIM) -> list:
    """A deterministic pseudo-random unit vector seeded by the text."""
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    vals = []
    counter = 0
    while len(vals) < dim:
        block = hashlib.sha256(seed + struct.pack(">I", counter)).digest()
        for i in range(0, len(block), 4):
            if len(vals) >= dim:
                break
            n = struct.unpack(">I", block[i:i + 4])[0]
            vals.append((n / 0xFFFFFFFF) * 2.0 - 1.0)
        counter += 1
    return _normalise(vals)


def embed_texts(texts: list, input_type: str, fake: bool = False) -> list:
    """Embed a batch of texts. input_type is 'document' or 'query'."""
    if fake:
        return [fake_embedding(t) for t in texts]
    voyage = get_voyage()
    for attempt in range(5):
        try:
            resp = voyage.embed(
                texts=texts,
                model=VOYAGE_MODEL,
                input_type=input_type,
                truncation=True,
                output_dimension=EMBEDDING_DIM,
            )
            return resp.embeddings
        except Exception as exc:  # noqa: BLE001 — retry only on rate limits
            if "rate" in str(exc).lower() and attempt < 4:
                wait = 2 ** attempt * 5
                print(f"  Rate limited, retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Exceeded embedding retries")


def embed_query(text: str, fake: bool = False) -> list:
    return embed_texts([text], input_type="query", fake=fake)[0]
