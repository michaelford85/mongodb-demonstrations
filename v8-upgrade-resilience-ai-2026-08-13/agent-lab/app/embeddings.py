"""Embeddings for the optional semantic ticket search.

Only needed when USE_VECTOR_SEARCH=true. Three backends behind one interface:

  voyage / openai  real embeddings from the provider.
  offline          deterministic hashed bag-of-words unit vectors. No key, no
                   network. Enough for the plumbing to be real; recall is not
                   meaningful, so the default search path is a regex scan.

All three return EMBEDDING_DIM-length unit vectors.
"""
import hashlib
import math
import re
import struct
import time

import config

_voyage = None
_openai = None

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "is", "are", "was", "were", "be", "been",
    "to", "of", "in", "on", "for", "with", "that", "this", "it", "as", "at",
    "by", "from", "but", "not", "no", "so", "if", "then", "than", "my", "our",
    "we", "i", "you", "they", "their", "its", "do", "does", "did", "can",
    "will", "would", "there", "when", "what", "why", "how", "has", "have",
}


def tokens(text: str) -> list:
    return [t for t in _TOKEN_RE.findall((text or "").lower())
            if t not in _STOPWORDS and len(t) > 2]


def _normalise(vec: list) -> list:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def offline_embedding(text: str, dim: int = None) -> list:
    """Signed hashing of the token bag — collisions stay unbiased."""
    dim = dim or config.EMBEDDING_DIM
    vec = [0.0] * dim
    for token in tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = struct.unpack(">I", digest[:4])[0] % dim
        vec[index] += 1.0 if digest[4] & 1 else -1.0
    if not any(vec):
        digest = hashlib.sha256((text or "empty").encode("utf-8")).digest()
        vec[struct.unpack(">I", digest[:4])[0] % dim] = 1.0
    return _normalise(vec)


def _get_voyage():
    global _voyage
    if _voyage is None:
        import voyageai

        key = config.embedding_api_key()
        if not key:
            raise RuntimeError("EMBEDDING_API_KEY is required for "
                               "EMBEDDING_PROVIDER=voyage")
        _voyage = voyageai.Client(api_key=key)
    return _voyage


def _get_openai():
    global _openai
    if _openai is None:
        from openai import OpenAI

        key = config.embedding_api_key()
        if not key:
            raise RuntimeError("EMBEDDING_API_KEY is required for "
                               "EMBEDDING_PROVIDER=openai")
        _openai = OpenAI(api_key=key)
    return _openai


def _embed_remote(texts: list, input_type: str) -> list:
    for attempt in range(5):
        try:
            if config.EMBEDDING_PROVIDER == "voyage":
                resp = _get_voyage().embed(
                    texts=texts,
                    model=config.EMBEDDING_MODEL,
                    input_type=input_type,
                    truncation=True,
                    output_dimension=config.EMBEDDING_DIM,
                )
                return resp.embeddings
            resp = _get_openai().embeddings.create(
                input=texts,
                model=config.EMBEDDING_MODEL,
                dimensions=config.EMBEDDING_DIM,
            )
            return [item.embedding for item in resp.data]
        except Exception as exc:  # noqa: BLE001 — retry rate limits only
            if "rate" in str(exc).lower() and attempt < 4:
                wait = 2 ** attempt * 5
                print(f"  Rate limited, retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Exceeded embedding retries")


def embed_texts(texts: list, input_type: str = "document") -> list:
    if config.EMBEDDING_PROVIDER == "offline":
        return [offline_embedding(t) for t in texts]
    return _embed_remote(texts, input_type)


def embed_query(text: str) -> list:
    return embed_texts([text], input_type="query")[0]
