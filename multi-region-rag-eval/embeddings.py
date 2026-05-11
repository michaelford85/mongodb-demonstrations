"""Simulated embedding function.

The real workload would call a hosted embedding API (for example Voyage AI's
``voyage-3`` at 1024 dimensions or ``voyage-3-large`` at 2000 dimensions). To
keep this demonstration self-contained and reproducible we use a deterministic
character n-gram hashing scheme that produces L2-normalised vectors of the same
shape. Misspellings of the same string share many n-grams, which is what makes
the fuzzy lookup behaviour observable end to end.
"""
from __future__ import annotations

import hashlib
from typing import Iterable

import numpy as np


def _ngrams(text: str, n: int = 3) -> Iterable[str]:
    cleaned = "".join(ch.lower() for ch in text if not ch.isspace())
    padded = f"^{cleaned}$"
    if len(padded) < n:
        yield padded
        return
    for i in range(len(padded) - n + 1):
        yield padded[i : i + n]


def _bucket(token: str, dim: int) -> tuple[int, float]:
    digest = hashlib.sha1(token.encode("utf-8")).digest()
    idx = int.from_bytes(digest[:4], "big") % dim
    sign = 1.0 if digest[4] & 1 else -1.0
    return idx, sign


def embed(text: str, dim: int) -> list[float]:
    """Return a deterministic, L2-normalised embedding for ``text``."""
    vector = np.zeros(dim, dtype=np.float32)
    for token in _ngrams(text, n=3):
        idx, sign = _bucket(token, dim)
        vector[idx] += sign
    for token in _ngrams(text, n=4):
        idx, sign = _bucket(token + "#4", dim)
        vector[idx] += 0.5 * sign
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        vector[0] = 1.0
        return vector.tolist()
    return (vector / norm).tolist()


def embed_account(account_name: str, product_group: str, dim: int) -> list[float]:
    """Compose the text used for indexing. Account name dominates the signal."""
    repeated = " ".join([account_name] * 3)
    return embed(f"{repeated} || {product_group}", dim)
