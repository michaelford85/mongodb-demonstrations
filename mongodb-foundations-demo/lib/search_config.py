"""Configuration for the Search & AI sections (⑧ MongoDB Search, ⑨ RAG).

The core walkthrough reads only `MONGODB_URI`. These sections add optional
knobs — the Voyage AI key that powers Automated Embedding and the client-side
reranker, and an optional generation model for the RAG answer step — all driven
by `.env` so the GUI, the setup scripts, and the README stay in sync.

The namespace stays fixed. Search and RAG live in one extra collection,
`knowledge_chunks`, inside the same demo database this project already owns, so
no code path here can point at a namespace the demo does not control.
"""

from __future__ import annotations

import os

from lib.mongo_client import DB_NAME, get_db

# ── Fixed namespace (owned by this demo, never env-driven) ───────────────────
KNOWLEDGE = "knowledge_chunks"

# The single text field that is BOTH BM25-indexed and autoEmbed-indexed, so the
# keyword and semantic legs see the same words and the comparison stays honest.
SEARCH_FIELD = "text"

# Index names are fixed so the mongosh snippets in the README run verbatim.
VECTOR_INDEX = "knowledge_vector_index"
TEXT_INDEX = "knowledge_text_index"

# ── Automated Embedding (Atlas embeds text at index- and query-time) ─────────
# The Voyage AI model Atlas uses for autoEmbed. Atlas holds the Voyage key you
# register in the Atlas project; the app never computes an embedding itself.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "voyage-4")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))

# ── App / query settings ─────────────────────────────────────────────────────
QUERY_LIMIT = int(os.getenv("QUERY_LIMIT", "5"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))

# ── AI retrieval — client-side reranking (optional) ──────────────────────────
# A Voyage AI cross-encoder re-scores retrieved candidates against the query.
# This is the one step that is NOT reproducible in mongosh, so it is optional:
# full-text, semantic, and hybrid all run without a key or the voyageai package.
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
VOYAGE_RERANK_MODEL = os.getenv("VOYAGE_RERANK_MODEL", "voyage-rerank-2")

# ── Generation — the RAG answer step (optional) ──────────────────────────────
# MongoDB is the retrieval half of RAG; the generation half is any LLM. The RAG
# section always shows the grounded context and the exact prompt, and calls an
# OpenAI-compatible endpoint for the final answer only when a key is configured.
GEN_API_KEY = os.getenv("GEN_API_KEY") or os.getenv("OPENAI_API_KEY")
GEN_BASE_URL = os.getenv("GEN_BASE_URL")  # e.g. an OpenAI-compatible gateway
GEN_MODEL = os.getenv("GEN_MODEL", "gpt-4o-mini")

_voyage_client = None
_llm_client = None


def get_knowledge():
    """Return the chunked-documents collection in the demo database."""
    return get_db()[KNOWLEDGE]


def knowledge_count() -> int:
    """Number of seeded chunks. 0 means the search corpus is not seeded yet."""
    return get_knowledge().count_documents({})


def is_seeded() -> bool:
    return get_knowledge().count_documents({}, limit=1) > 0


def rerank_available() -> bool:
    """True when the optional Voyage reranker can run (key present)."""
    return bool(VOYAGE_API_KEY)


def generation_available() -> bool:
    """True when the optional RAG generation step is configured (key present)."""
    return bool(GEN_API_KEY)


def get_voyage():
    """Lazily build a Voyage AI client for the reranker. Optional dependency."""
    global _voyage_client
    if _voyage_client is None:
        if not VOYAGE_API_KEY:
            raise RuntimeError(
                "VOYAGE_API_KEY is not set. Only the AI-retrieval (rerank) step "
                "needs it; full-text, semantic, and hybrid search do not."
            )
        try:
            import voyageai
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "voyageai is not installed. Run: pip install -r requirements.txt"
            ) from exc
        _voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)
    return _voyage_client


def get_llm():
    """Lazily build an OpenAI-compatible client for the RAG answer step.

    Optional: the RAG section is fully functional without it, showing the
    retrieved grounding and the assembled prompt. Generation only runs when a
    key is configured and the `openai` package is installed.
    """
    global _llm_client
    if _llm_client is None:
        if not GEN_API_KEY:
            raise RuntimeError(
                "No generation key set. The RAG section still retrieves context "
                "and builds the prompt; set GEN_API_KEY to also generate an "
                "answer."
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "openai is not installed. Run: pip install -r requirements.txt"
            ) from exc
        kwargs = {"api_key": GEN_API_KEY}
        if GEN_BASE_URL:
            kwargs["base_url"] = GEN_BASE_URL
        _llm_client = OpenAI(**kwargs)
    return _llm_client


def namespace() -> dict:
    """Presenter-friendly summary of what these sections use."""
    return {
        "database": DB_NAME,
        "collection": KNOWLEDGE,
        "search_field": SEARCH_FIELD,
        "vector_index": VECTOR_INDEX,
        "text_index": TEXT_INDEX,
        "embedding_model": EMBEDDING_MODEL,
        "rerank_model": VOYAGE_RERANK_MODEL,
    }
