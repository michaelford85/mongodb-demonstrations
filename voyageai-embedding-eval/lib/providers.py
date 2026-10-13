"""Embedding provider adapters.

Each adapter speaks its provider's real embedding API (they are NOT all
OpenAI-compatible) and maps our two input modes — "document" and "query" — onto
the provider's own parameter:

    provider   endpoint                          document / query parameter
    ---------  --------------------------------  ----------------------------------
    voyage     POST {base}/embeddings            input_type = document | query
    openai     POST {base}/embeddings            (none — same input for both)
    cohere     POST {base}/v2/embed              input_type = search_document | search_query
    gemini     POST {base}/models/M:batchEmbedContents
                                                 taskType = RETRIEVAL_DOCUMENT | RETRIEVAL_QUERY

Vectors are returned exactly as the provider produced them: never truncated,
padded, or re-normalised here. Output dimension is only ever requested through a
provider's documented parameter.
"""
from __future__ import annotations

import math
import random
import time
from typing import Callable

import requests

from lib.config import EvalError, ProviderConfig

DOCUMENT, QUERY = "document", "query"
TIMEOUT_SECONDS = 60
MAX_RETRIES = 5


class ProviderError(EvalError):
    """A provider call failed; the message never contains credentials."""


class EmbeddingProvider:
    """Base adapter: batching, retry/backoff, and response validation."""

    name = "base"
    batch_size = 64
    default_base_url = ""

    def __init__(self, cfg: ProviderConfig):
        self.cfg = cfg
        self.base_url = (cfg.base_url or self.default_base_url).rstrip("/")
        self.model = cfg.model
        self._session = requests.Session()
        self._sleep: Callable[[float], None] = time.sleep

    # ---- identity ---------------------------------------------------------
    @property
    def label(self) -> str:
        return f"{self.name}:{self.model}"

    def cache_key_prefix(self, input_type: str) -> str:
        """Everything except the text that changes the returned vector."""
        return "|".join([self.name, self.base_url, self.model,
                         str(self.cfg.output_dimension or "default"), input_type,
                         repr(self._prefix(input_type))])

    def _prefix(self, input_type: str) -> str:
        return self.cfg.document_prefix if input_type == DOCUMENT else self.cfg.query_prefix

    # ---- provider-specific hooks -----------------------------------------
    def _request(self, texts: list[str], input_type: str) -> tuple[str, dict, dict]:
        """Return (url, headers, json_body)."""
        raise NotImplementedError

    def _parse(self, payload: dict, expected: int) -> list[list[float]]:
        raise NotImplementedError

    # ---- shared machinery -------------------------------------------------
    def embed(self, texts: list[str], input_type: str,
              on_batch: Callable[[int, int], None] | None = None) -> list[list[float]]:
        if input_type not in (DOCUMENT, QUERY):
            raise ValueError(f"input_type must be '{DOCUMENT}' or '{QUERY}'")
        prefix = self._prefix(input_type)
        if prefix:
            texts = [prefix + t for t in texts]
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            vectors.extend(self._embed_batch(batch, input_type))
            if on_batch:
                on_batch(min(start + len(batch), len(texts)), len(texts))
        self._check_dimensions(vectors)
        return vectors

    def _embed_batch(self, batch: list[str], input_type: str) -> list[list[float]]:
        url, headers, body = self._request(batch, input_type)
        payload = self._post_with_retry(url, headers, body)
        vectors = self._parse(payload, len(batch))
        if len(vectors) != len(batch):
            raise ProviderError(f"{self.label}: asked for {len(batch)} embeddings, got {len(vectors)}.")
        return vectors

    def _check_dimensions(self, vectors: list[list[float]]) -> None:
        dims = {len(v) for v in vectors}
        if len(dims) > 1:
            raise ProviderError(f"{self.label}: inconsistent vector lengths {sorted(dims)}.")
        if dims:
            dim = dims.pop()
            want = self.cfg.output_dimension
            if want and dim != want:
                raise ProviderError(
                    f"{self.label}: requested output dimension {want} but received {dim}. "
                    "The model may not support that dimension; check the provider docs."
                )
            if dim == 0 or any(not math.isfinite(x) for v in vectors for x in v):
                raise ProviderError(f"{self.label}: received empty or non-finite embeddings.")

    def _post_with_retry(self, url: str, headers: dict, body: dict) -> dict:
        last = ""
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self._session.post(url, headers=headers, json=body, timeout=TIMEOUT_SECONDS)
            except requests.RequestException as exc:
                last = f"network error ({type(exc).__name__})"
            else:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError:
                        raise ProviderError(f"{self.label}: response was not valid JSON.") from None
                if resp.status_code in (401, 403):
                    raise ProviderError(
                        f"{self.label}: authentication failed (HTTP {resp.status_code}). Check the API key, "
                        "that it matches the endpoint (Atlas model keys vs. Voyage-issued keys), "
                        "and that it has access to this model."
                    )
                if resp.status_code not in (429, 500, 502, 503, 504):
                    raise ProviderError(
                        f"{self.label}: HTTP {resp.status_code}: {self._safe_detail(resp)}"
                    )
                last = f"HTTP {resp.status_code}"
                if attempt < MAX_RETRIES:
                    self._sleep(self._backoff(attempt, resp.headers.get("Retry-After")))
                    continue
            if attempt < MAX_RETRIES:
                self._sleep(self._backoff(attempt, None))
        raise ProviderError(f"{self.label}: giving up after {MAX_RETRIES + 1} attempts ({last}).")

    @staticmethod
    def _backoff(attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), 60.0)
            except ValueError:
                pass
        return min(2.0 ** attempt, 30.0) + random.uniform(0, 0.5)

    def _safe_detail(self, resp) -> str:
        """Short error text from the body, with the key scrubbed if echoed."""
        try:
            data = resp.json()
            msg = data.get("detail") or data.get("message") or data.get("error") or data
            if isinstance(msg, dict):
                msg = msg.get("message") or str(msg)
        except ValueError:
            msg = resp.text
        text = str(msg)[:300]
        key = self.cfg.api_key
        return text.replace(key, "***") if key else text


class VoyageProvider(EmbeddingProvider):
    name = "voyage"
    batch_size = 64
    default_base_url = "https://ai.mongodb.com/v1"

    def _request(self, texts, input_type):
        body = {"input": texts, "model": self.model, "input_type": input_type, "truncation": True}
        if self.cfg.output_dimension:
            body["output_dimension"] = self.cfg.output_dimension
        headers = {"Authorization": f"Bearer {self.cfg.api_key}", "Content-Type": "application/json"}
        return f"{self.base_url}/embeddings", headers, body

    def _parse(self, payload, expected):
        try:
            items = sorted(payload["data"], key=lambda d: d["index"])
            return [d["embedding"] for d in items]
        except (KeyError, TypeError):
            raise ProviderError("voyage: unexpected response shape (no data[].embedding).") from None


class OpenAIProvider(EmbeddingProvider):
    """OpenAI /v1/embeddings (and servers that implement the same shape)."""
    name = "openai"
    batch_size = 128
    default_base_url = "https://api.openai.com/v1"

    def _request(self, texts, input_type):
        body = {"model": self.model, "input": texts, "encoding_format": "float"}
        if self.cfg.output_dimension:
            body["dimensions"] = self.cfg.output_dimension
        headers = {"Authorization": f"Bearer {self.cfg.api_key}", "Content-Type": "application/json"}
        return f"{self.base_url}/embeddings", headers, body

    def _parse(self, payload, expected):
        try:
            items = sorted(payload["data"], key=lambda d: d["index"])
            return [d["embedding"] for d in items]
        except (KeyError, TypeError):
            raise ProviderError("openai: unexpected response shape (no data[].embedding).") from None


class CohereProvider(EmbeddingProvider):
    name = "cohere"
    batch_size = 96  # API maximum texts per call
    default_base_url = "https://api.cohere.com"
    _INPUT_TYPES = {DOCUMENT: "search_document", QUERY: "search_query"}

    def _request(self, texts, input_type):
        body = {"model": self.model, "texts": texts, "input_type": self._INPUT_TYPES[input_type],
                "embedding_types": ["float"], "truncate": "END"}
        if self.cfg.output_dimension:
            body["output_dimension"] = self.cfg.output_dimension
        headers = {"Authorization": f"Bearer {self.cfg.api_key}", "Content-Type": "application/json"}
        return f"{self.base_url}/v2/embed", headers, body

    def _parse(self, payload, expected):
        try:
            return payload["embeddings"]["float"]
        except (KeyError, TypeError):
            raise ProviderError("cohere: unexpected response shape (no embeddings.float).") from None


class GeminiProvider(EmbeddingProvider):
    name = "gemini"
    batch_size = 100  # batchEmbedContents maximum requests per call
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"
    _TASK_TYPES = {DOCUMENT: "RETRIEVAL_DOCUMENT", QUERY: "RETRIEVAL_QUERY"}

    def _model_path(self) -> str:
        return self.model if self.model.startswith("models/") else f"models/{self.model}"

    def _request(self, texts, input_type):
        requests_ = []
        for text in texts:
            item = {"model": self._model_path(), "content": {"parts": [{"text": text}]},
                    "taskType": self._TASK_TYPES[input_type]}
            if self.cfg.output_dimension:
                item["outputDimensionality"] = self.cfg.output_dimension
            requests_.append(item)
        # Key goes in a header, never in the URL, so it cannot leak into logs.
        headers = {"x-goog-api-key": self.cfg.api_key, "Content-Type": "application/json"}
        return f"{self.base_url}/{self._model_path()}:batchEmbedContents", headers, {"requests": requests_}

    def _parse(self, payload, expected):
        try:
            return [e["values"] for e in payload["embeddings"]]
        except (KeyError, TypeError):
            raise ProviderError("gemini: unexpected response shape (no embeddings[].values).") from None


PROVIDERS: dict[str, type[EmbeddingProvider]] = {
    "voyage": VoyageProvider,
    "openai": OpenAIProvider,
    "cohere": CohereProvider,
    "gemini": GeminiProvider,
}


def build_provider(cfg: ProviderConfig) -> EmbeddingProvider:
    try:
        return PROVIDERS[cfg.provider](cfg)
    except KeyError:
        raise ProviderError(
            f"Unsupported provider '{cfg.provider}'. Supported: {', '.join(PROVIDERS)}."
        ) from None
