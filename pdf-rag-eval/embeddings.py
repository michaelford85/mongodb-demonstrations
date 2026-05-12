"""Voyage AI embedding helpers shared by both backends.

Mirrors the pattern used in multi-region-rag-eval/embeddings.py so that
both demos exercise identical client-side embedding behaviour: batched
calls, exponential backoff on rate-limit errors, and `output_dimension`
forwarded only for the flexible-dimension models.
"""
from __future__ import annotations

import time
from functools import lru_cache

import voyageai
from voyageai.error import RateLimitError

# Models that accept the ``output_dimension`` argument. Other Voyage models
# only emit their native dimension and reject the parameter outright.
_FLEXIBLE_DIM_MODELS = frozenset(
    {
        "voyage-4-large",
        "voyage-4",
        "voyage-4-lite",
        "voyage-3-large",
        "voyage-3.5",
        "voyage-3.5-lite",
        "voyage-code-3",
    }
)

# Voyage's embeddings endpoint accepts up to 128 inputs per request.
EMBED_BATCH_SIZE = 128


@lru_cache(maxsize=1)
def _client(api_key: str) -> voyageai.Client:
    return voyageai.Client(api_key=api_key)


def _embed_kwargs(model: str, dim: int) -> dict:
    kwargs: dict = {"model": model}
    if model in _FLEXIBLE_DIM_MODELS:
        kwargs["output_dimension"] = dim
    return kwargs


def _embed_with_retry(
    client: voyageai.Client,
    texts: list[str],
    input_type: str,
    model: str,
    dim: int,
    max_attempts: int = 5,
) -> list[list[float]]:
    delay = 1.0
    for attempt in range(1, max_attempts + 1):
        try:
            result = client.embed(
                texts,
                input_type=input_type,
                **_embed_kwargs(model, dim),
            )
            return result.embeddings
        except RateLimitError:
            if attempt == max_attempts:
                raise
            time.sleep(delay)
            delay *= 2.0
    raise RuntimeError("unreachable")


def embed_chunks(
    texts: list[str], api_key: str, model: str, dim: int
) -> list[list[float]]:
    """Embed a list of document chunks (input_type='document'), batched."""
    client = _client(api_key)
    out: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        out.extend(_embed_with_retry(client, batch, "document", model, dim))
    return out


def embed_query(text: str, api_key: str, model: str, dim: int) -> list[float]:
    """Embed a single user query (input_type='query')."""
    client = _client(api_key)
    return _embed_with_retry(client, [text], "query", model, dim)[0]
