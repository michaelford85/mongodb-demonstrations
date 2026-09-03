"""Pluggable embedding backend for the Semantic and Hybrid search modes.

Two backends ship in the box, selected with ``EMBEDDING_PROVIDER``:

    local   (default)  Zero-dependency, deterministic feature-hashing embedder.
                       No API key required, so the demo runs out of the box.
                       Cosine similarity reflects shared catalog vocabulary,
                       which is enough to make semantic retrieval feel real.
    voyage             Voyage AI embeddings. Requires ``pip install voyageai``
                       and ``VOYAGE_API_KEY`` (read server-side only).

Ingestion and query paths share the same instance, so vectors always come from
an identical pipeline.
"""

import hashlib
import math
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def embedding_dim() -> int:
    return int(os.getenv("EMBEDDING_DIM", "256"))


def provider_name() -> str:
    return os.getenv("EMBEDDING_PROVIDER", "local").lower()


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


class LocalEmbedder:
    """Deterministic feature-hashing (the hashing trick) embedder.

    Each token is hashed to a dimension and a sign, term frequencies are summed,
    and the vector is L2-normalized. Products that share vocabulary end up with
    a high cosine similarity, so a paraphrased shopper question still retrieves
    the right products — with no external service and no API key.
    """

    provider = "local"

    def __init__(self, dim: int | None = None):
        self.dim = dim or embedding_dim()

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _tokenize(text):
            # Deterministic across processes (unlike the salted built-in hash),
            # so seed-time and query-time vectors always match.
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            h = int.from_bytes(digest, "big")
            vec[h % self.dim] += 1.0 if (h >> 8) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


class VoyageEmbedder:
    """Voyage AI embeddings. Isolated so the paid dependency stays optional."""

    provider = "voyage"

    def __init__(self, dim: int | None = None):
        import voyageai  # imported lazily so `local` needs no dependency

        self.dim = dim or embedding_dim()
        self.model = os.getenv("VOYAGE_MODEL", "voyage-3.5")
        api_key = os.getenv("VOYAGE_API_KEY")
        if not api_key:
            raise ValueError(
                "EMBEDDING_PROVIDER=voyage requires VOYAGE_API_KEY in .env."
            )
        self._client = voyageai.Client(api_key=api_key)

    def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        result = self._client.embed(
            texts, model=self.model,
            input_type=input_type, output_dimension=self.dim,
        )
        return result.embeddings

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "document")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "query")[0]


_embedder = None


def get_embedder():
    """Return a cached embedder for the configured provider."""
    global _embedder
    if _embedder is None:
        provider = provider_name()
        if provider == "voyage":
            _embedder = VoyageEmbedder()
        elif provider == "local":
            _embedder = LocalEmbedder()
        else:
            raise ValueError(
                f"Unknown EMBEDDING_PROVIDER '{provider}'. Use 'local' or 'voyage'."
            )
    return _embedder


def reset_embedder() -> None:
    """Drop the cached embedder (used after a provider change)."""
    global _embedder
    _embedder = None


def product_text(product: dict) -> str:
    """Text embedded for a product — identical on the ingest and query paths."""
    parts = [
        product.get("name", ""),
        product.get("summary", ""),
        product.get("description", ""),
        " ".join(product.get("tags", []) or []),
        product.get("category", ""),
        product.get("product_type", "").replace("_", " "),
        " ".join(product.get("entitlements", []) or []),
    ]
    return " \n".join(p for p in parts if p)
