"""Offline stand-ins used by the dry run and tests. NOTHING here is a real model.

`MockProvider` hashes words into a fixed-size vector, so texts that share words
land close together — enough to exercise ingestion, retrieval and metrics end to
end without network access, credentials, or cost. Its scores say nothing about
real embedding quality.
"""
from __future__ import annotations

import hashlib
import math
import random

from lib.config import ProviderConfig
from lib.dataset import Dataset
from lib.providers import EmbeddingProvider

TOPICS = {
    "astronomy": ["telescope", "orbit", "galaxy", "comet", "nebula", "planet", "eclipse", "star"],
    "cooking": ["simmer", "dough", "recipe", "spice", "oven", "broth", "whisk", "garnish"],
    "gardening": ["compost", "seedling", "pruning", "mulch", "trellis", "harvest", "soil", "bloom"],
    "sailing": ["keel", "mast", "harbor", "tide", "rigging", "anchor", "voyage", "rudder"],
    "music": ["melody", "chord", "tempo", "harmony", "rhythm", "octave", "cadence", "lyric"],
    "geology": ["basalt", "fault", "mineral", "erosion", "strata", "magma", "quartz", "glacier"],
    "chess": ["gambit", "endgame", "castling", "opening", "bishop", "tactic", "pawn", "fork"],
    "weather": ["humidity", "front", "storm", "pressure", "monsoon", "drizzle", "gust", "frost"],
}
FILLER = ["the", "a", "of", "and", "about", "notes", "overview", "study", "guide", "review"]


class MockProvider(EmbeddingProvider):
    name = "mock"
    batch_size = 64

    def __init__(self, cfg: ProviderConfig, dim: int, noise: float = 0.0):
        super().__init__(cfg)
        self.dim, self.noise = dim, noise

    def cache_key_prefix(self, input_type: str) -> str:  # never cached
        return f"mock|{self.model}|{self.dim}|{input_type}"

    def embed(self, texts, input_type, on_batch=None):
        out = [self._vector(t) for t in texts]
        if on_batch:
            on_batch(len(texts), len(texts))
        return out

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for word in text.lower().split():
            digest = hashlib.sha256(f"{self.model}:{word}".encode()).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            vec[idx] += 1.0 if digest[4] % 2 else -1.0
        if self.noise:
            rng = random.Random(f"{self.model}:{text}")
            vec = [v + rng.gauss(0, self.noise) for v in vec]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def synthetic_dataset(seed: int = 42) -> Dataset:
    """Tiny made-up corpus: 8 topics x 8 documents, 2 queries per topic."""
    rng = random.Random(seed)
    corpus, queries, qrels = {}, {}, {}
    for topic, words in TOPICS.items():
        doc_ids = []
        for i in range(8):
            body = rng.sample(words, 4) + rng.sample(FILLER, 3)
            rng.shuffle(body)
            did = f"{topic}-d{i}"
            corpus[did] = {"title": f"{topic.title()} note {i}", "text": " ".join(body)}
            doc_ids.append(did)
        for j in range(2):
            qid = f"{topic}-q{j}"
            queries[qid] = " ".join(rng.sample(words, 3))
            qrels[qid] = {d: 1 for d in doc_ids}
    return Dataset("synthetic", corpus, queries, qrels,
                   ["Synthetic data generated locally; no real benchmark or model involved."])
