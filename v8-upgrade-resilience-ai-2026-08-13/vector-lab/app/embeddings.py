"""Embedding backends behind one interface.

  voyage   real embeddings from the provider named by EMBEDDING_MODEL.
  openai   ditto, via the OpenAI embeddings endpoint.
  offline  a local "concept hash" embedding: tokens are expanded through a
           small synonym table, then hashed into EMBEDDING_DIM buckets. No key,
           no network, no cost. It is not a language model, but because the
           synonym table connects the way people ask ("bill went up") to the
           way the articles are written ("proration", "statement"), the
           keyword-versus-vector gap the lab teaches is still visible.

All three return EMBEDDING_DIM-length unit vectors, so the same vector index
definition accepts any of them.
"""
import hashlib
import math
import re
import struct
import time

import config

_voyage = None
_openai = None

# Bridges colloquial phrasing to the vocabulary the corpus actually uses. This
# is the offline backend's entire "understanding" — deliberately small and
# readable so a workshop can see exactly why a result ranked where it did.
CONCEPTS = {
    "bill": "billing charge statement invoice cost amount",
    "invoice": "billing charge statement invoice",
    "charge": "billing charge statement amount",
    "higher": "increase more expensive change difference",
    "expensive": "increase more cost charge",
    "month": "cycle period statement monthly",
    "cycle": "cycle period monthly proration",
    "proration": "proration cycle period split charge seat",
    "seat": "seat membership member teammate licence",
    "quits": "leaves removal membership seat offboarding",
    "leaves": "leaves removal membership seat offboarding",
    "quit": "leaves removal membership seat offboarding",
    "login": "signin session authentication access provider",
    "log": "signin session authentication access",
    "signin": "signin session authentication provider federated",
    "signing": "signin session authentication provider federated",
    "session": "signin session authentication access",
    "sessions": "signin session authentication access",
    "password": "credential authentication signin",
    "passwords": "credential authentication signin",
    "provider": "identity provider federated metadata authentication",
    "providers": "identity provider federated metadata authentication",
    "identity": "identity provider federated authentication",
    "federated": "identity provider federated authentication signin",
    "people": "people user member teammate audience",
    "changed": "change difference switched",
    "switched": "change difference switched provider",
    "accepted": "acknowledged accepted queued delivery",
    "request": "request payload message delivery endpoint",
    "downstream": "destination endpoint receiving delivery",
    "never": "missing absent failure",
    "dashboard": "dashboard summary view reporting",
    "download": "export file reporting extract",
    "export": "export file reporting extract",
    "total": "total figure number summary",
    "match": "disagree difference discrepancy compare",
    "slow": "slow sluggish latency performance responsiveness",
    "slows": "slow sluggish latency performance responsiveness",
    "sluggish": "slow latency performance responsiveness",
    "afternoon": "afternoon hourly schedule digest queue",
    "lunch": "afternoon hourly schedule digest",
    "retry": "retry attempt backoff redelivery",
    "queue": "queue backlog schedule digest",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "is", "are", "was", "were", "be", "been",
    "to", "of", "in", "on", "for", "with", "that", "this", "it", "as", "at",
    "by", "from", "but", "not", "no", "so", "if", "then", "than", "my", "our",
    "we", "i", "you", "they", "their", "its", "do", "does", "did", "can",
    "will", "would", "there", "when", "what", "why", "how", "has", "have",
}


def _tokens(text: str) -> list:
    return [t for t in _TOKEN_RE.findall(text.lower())
            if t not in _STOPWORDS and len(t) > 2]


def _expand(tokens: list) -> list:
    """Each token contributes itself plus any concept terms it maps to."""
    out = []
    for tok in tokens:
        out.append(tok)
        expansion = CONCEPTS.get(tok)
        if expansion:
            out.extend(expansion.split())
    return out


def _bucket(token: str, dim: int) -> tuple:
    """Map a token to (index, sign) — signed hashing keeps collisions unbiased."""
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    index = struct.unpack(">I", digest[:4])[0] % dim
    sign = 1.0 if digest[4] & 1 else -1.0
    return index, sign


def _normalise(vec: list) -> list:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def offline_embedding(text: str, dim: int = None) -> list:
    dim = dim or config.EMBEDDING_DIM
    vec = [0.0] * dim
    for token in _expand(_tokens(text)):
        index, sign = _bucket(token, dim)
        vec[index] += sign
    if not any(vec):
        # An all-stopword string still needs a stable, valid vector.
        index, sign = _bucket(text.strip().lower() or "empty", dim)
        vec[index] = sign
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
    provider = config.EMBEDDING_PROVIDER
    for attempt in range(5):
        try:
            if provider == "voyage":
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
