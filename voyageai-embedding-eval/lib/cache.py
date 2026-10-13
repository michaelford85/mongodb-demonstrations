"""On-disk embedding cache (SQLite), keyed by provider + model + config + text.

Safe by construction: the key is a SHA-256 over the provider identity, endpoint,
model, requested dimension, input mode and the exact text, so a different model,
dimension, mode or text can never hit another entry. Only public benchmark text
is embedded here; the cache stores hashes and float vectors, never API keys.
Delete the cache directory at any time to start fresh.
"""
from __future__ import annotations

import hashlib
import sqlite3
from array import array
from pathlib import Path


def cache_key(prefix: str, text: str) -> str:
    return hashlib.sha256(f"{prefix}\x00{text}".encode("utf-8")).hexdigest()


class EmbeddingCache:
    def __init__(self, directory: str | Path):
        self.path = Path(directory) / "embeddings.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS emb (key TEXT PRIMARY KEY, vec BLOB NOT NULL)")

    def _connect(self):
        return sqlite3.connect(self.path)

    def get_many(self, keys: list[str]) -> dict[str, list[float]]:
        found: dict[str, list[float]] = {}
        with self._connect() as db:
            for i in range(0, len(keys), 500):
                chunk = keys[i:i + 500]
                marks = ",".join("?" * len(chunk))
                for key, blob in db.execute(f"SELECT key, vec FROM emb WHERE key IN ({marks})", chunk):
                    vec = array("f")
                    vec.frombytes(blob)
                    found[key] = vec.tolist()
        return found

    def put_many(self, items: dict[str, list[float]]) -> None:
        with self._connect() as db:
            db.executemany("INSERT OR REPLACE INTO emb VALUES (?, ?)",
                           [(k, array("f", v).tobytes()) for k, v in items.items()])
