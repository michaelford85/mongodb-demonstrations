"""Knowledge Assistant: retrieval-first, then optionally grounded by Claude.

Order of operations is deliberate: retrieve synthetic guidance from Atlas Vector
Search *first*, then pass only the retrieved context plus the question to Claude.
Keys are read server-side only. With no ANTHROPIC_API_KEY the assistant still
runs retrieval and returns a clearly-labelled extractive answer built solely
from the retrieved snippets — never a free-form model answer.
"""

from __future__ import annotations

import math
import os

from pymongo.database import Database

from lib.atlas_client import KNOWLEDGE_COLLECTION
from lib.embeddings import get_embedder, provider_name
from lib.queries import VECTOR_INDEX

DEFAULT_MODEL = "claude-haiku-4-5"  # Anthropic's current lowest-cost model


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


def _brute_force(db: Database, qvec: list[float], limit: int) -> list[dict]:
    """Cosine fallback over stored embeddings when the Atlas index isn't ready.

    Keeps the demo working the moment data is seeded, before the vector index
    finishes building. The UI clearly labels which path produced the hits.
    """
    docs = list(db[KNOWLEDGE_COLLECTION].find(
        {"embedding": {"$exists": True}}, {"embedding": 1, "title": 1,
         "body": 1, "crop": 1, "category": 1, "note_id": 1, "_id": 0}))
    scored = [(_cosine(qvec, d.pop("embedding")), d) for d in docs]
    scored.sort(key=lambda s: s[0], reverse=True)
    out = []
    for score, d in scored[:limit]:
        out.append({**d, "score": round(score, 4)})
    return out


def retrieve(db: Database, question: str, limit: int = 4) -> dict:
    """Vector-search the synthetic corpus; fall back to brute-force cosine."""
    qvec = get_embedder().embed_query(question)
    pipeline = [
        {"$vectorSearch": {"index": VECTOR_INDEX, "path": "embedding",
                           "queryVector": qvec,
                           "numCandidates": max(limit * 15, 60), "limit": limit}},
        {"$project": {"_id": 0, "embedding": 0}},
        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
    ]
    try:
        rows = list(db[KNOWLEDGE_COLLECTION].aggregate(pipeline))
        if rows:
            for r in rows:
                r["score"] = round(r.get("score", 0.0), 4)
            return {"sources": rows, "path": "atlas_vector_search"}
    except Exception:
        pass
    return {"sources": _brute_force(db, qvec, limit), "path": "brute_force_cosine"}


def claude_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _context_block(sources: list[dict]) -> str:
    return "\n\n".join(
        f"[{s.get('note_id')}] {s.get('title')}\n{s.get('body')}"
        for s in sources)


def _extractive_answer(question: str, sources: list[dict]) -> str:
    if not sources:
        return "No matching guidance was retrieved from the demo corpus."
    lead = sources[0]
    return (f"Based only on the retrieved demo notes, the most relevant guidance "
            f"is **{lead.get('title')}**: {lead.get('body')} "
            f"(see also {', '.join(s.get('note_id') for s in sources[1:])}).")


def generate(question: str, sources: list[dict]) -> dict:
    """Grounded answer. Uses Claude when a key is present, else extractive."""
    if not claude_available():
        return {"mode": "extractive", "model": None,
                "answer": _extractive_answer(question, sources)}
    try:
        import anthropic

        model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        prompt = (
            "You are a cautious assistant for an agriculture residue-risk demo. "
            "Answer ONLY using the numbered context notes below. If the context "
            "is insufficient, say so. Do not add outside facts.\n\n"
            f"Context:\n{_context_block(sources)}\n\nQuestion: {question}")
        msg = client.messages.create(
            model=model, max_tokens=400,
            messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if b.type == "text")
        return {"mode": "claude", "model": model, "answer": text}
    except Exception as e:  # noqa: BLE001 — degrade gracefully in a live demo
        return {"mode": "extractive", "model": None,
                "answer": _extractive_answer(question, sources),
                "error": str(e)}


def ask(db: Database, question: str, limit: int = 4) -> dict:
    """Retrieve first, then generate a grounded answer."""
    retrieval = retrieve(db, question, limit)
    answer = generate(question, retrieval["sources"])
    return {**retrieval, **answer, "provider": provider_name()}
