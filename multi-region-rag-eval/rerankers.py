"""Voyage AI reranking helper.

A bi-encoder vector search returns the K most plausible candidates via a
single cosine/dot-product comparison in embedding space; a cross-encoder
reranker re-scores each (query, candidate) pair jointly with full
attention over both texts, producing a tighter relevance signal at the
cost of one extra API call per query.

The same Voyage SDK client is used for embeddings and reranking but a
separate ``lru_cache`` keeps the two call sites independent.
"""
from __future__ import annotations

import time
from functools import lru_cache
from typing import Callable

import voyageai
from voyageai.error import RateLimitError

DEFAULT_RERANK_MODEL = "rerank-2.5"


@lru_cache(maxsize=1)
def _client(api_key: str) -> voyageai.Client:
    return voyageai.Client(api_key=api_key)


def _candidate_text(c: dict) -> str:
    # Natural-language form for a cross-encoder. The repeated-name trick
    # that ``embeddings.compose_account_text`` uses to bias a bi-encoder
    # toward the name signal is unnecessary here: a cross-encoder attends
    # over the full (query, candidate) pair jointly.
    return f"{c['account_name']} ({c['product_group']})"


def rerank(
    query: str,
    candidates: list[dict],
    api_key: str,
    model: str,
    top_k: int | None = None,
    text_fn: Callable[[dict], str] = _candidate_text,
    max_attempts: int = 5,
) -> tuple[list[dict], float]:
    """Re-score and re-order candidates with Voyage rerank.

    Returns ``(reranked_rows, elapsed_ms)``. Each row in ``reranked_rows``
    is a shallow copy of the corresponding input dict with a
    ``rerank_score`` float added. Order is descending by ``rerank_score``;
    truncated to ``top_k`` if set.
    """
    if not candidates:
        return [], 0.0
    client = _client(api_key)
    docs = [text_fn(c) for c in candidates]
    delay = 1.0
    start = time.perf_counter()
    result = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = client.rerank(
                query=query,
                documents=docs,
                model=model,
                top_k=top_k,
            )
            break
        except RateLimitError:
            if attempt == max_attempts:
                raise
            time.sleep(delay)
            delay *= 2.0
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    assert result is not None
    out: list[dict] = []
    for r in result.results:
        merged = dict(candidates[r.index])
        merged["rerank_score"] = r.relevance_score
        out.append(merged)
    return out, elapsed_ms
