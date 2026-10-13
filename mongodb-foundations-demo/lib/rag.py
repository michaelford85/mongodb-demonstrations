"""Retrieval-augmented generation over the chunked corpus.

This is the "how MongoDB Search fits into RAG" story, end to end and honest
about the boundary: MongoDB owns retrieval (vector or hybrid over the chunks),
the app assembles a grounded context and the exact prompt, and generation — the
only non-MongoDB step — runs against an LLM when one is configured. When it is
not, the section still shows the retrieved grounding and the prompt, which is
the part MongoDB actually powers.
"""

from __future__ import annotations

from lib.search import hybrid_search, semantic_search
from lib.search_config import GEN_MODEL, RAG_TOP_K, SEARCH_FIELD, get_llm

STRATEGIES = {"semantic": semantic_search, "hybrid": hybrid_search}

SYSTEM_PROMPT = (
    "You are a support assistant for the Example Cloud Platform. Answer the "
    "user's question using ONLY the numbered context passages provided. Cite "
    "the passages you use with their bracketed numbers, e.g. [1]. If the "
    "context does not contain the answer, say you do not have that information "
    "rather than guessing."
)


def retrieve(question: str, strategy: str = "hybrid", k: int = RAG_TOP_K):
    """Retrieve the top-k grounding chunks for a question. Returns (chunks, pipeline)."""
    search = STRATEGIES.get(strategy, hybrid_search)
    return search(question, limit=k)


def build_context(chunks: list):
    """Turn retrieved chunks into a numbered context block and a citation list."""
    lines, citations = [], []
    for i, chunk in enumerate(chunks, start=1):
        title = chunk.get("doc_title", "")
        section = chunk.get("section", "")
        text = " ".join(chunk.get(SEARCH_FIELD, "").split())
        lines.append("[{}] ({} — {})\n{}".format(i, title, section, text))
        citations.append({
            "ref": i,
            "doc_id": chunk.get("doc_id"),
            "doc_title": title,
            "section": section,
            "chunk_index": chunk.get("chunk_index"),
        })
    return "\n\n".join(lines), citations


def build_prompt(question: str, context: str):
    """Assemble the chat messages and a readable rendering of the full prompt."""
    user = ("Context passages:\n\n{}\n\n"
            "Question: {}\n\n"
            "Answer, citing the passages you used.").format(context, question)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    rendered = "SYSTEM:\n{}\n\nUSER:\n{}".format(SYSTEM_PROMPT, user)
    return messages, rendered


def generate(messages: list) -> str:
    """Call the configured LLM for the final answer. Optional — needs a key."""
    client = get_llm()
    response = client.chat.completions.create(
        model=GEN_MODEL, messages=messages, temperature=0)
    return response.choices[0].message.content


def answer(question: str, strategy: str = "hybrid", k: int = RAG_TOP_K,
           do_generate: bool = False) -> dict:
    """Run the full RAG flow and return every intermediate artifact.

    `generated` is None unless `do_generate` is set and an LLM is configured;
    `generation_error` carries a readable reason when generation was requested
    but could not run, so the UI can explain it without failing the retrieval.
    """
    chunks, pipeline = retrieve(question, strategy=strategy, k=k)
    context, citations = build_context(chunks)
    messages, rendered = build_prompt(question, context)

    result = {
        "question": question,
        "strategy": strategy,
        "chunks": chunks,
        "pipeline": pipeline,
        "context": context,
        "citations": citations,
        "messages": messages,
        "prompt": rendered,
        "generated": None,
        "generation_error": None,
    }

    if do_generate and chunks:
        try:
            result["generated"] = generate(messages)
        except Exception as exc:  # noqa: BLE001 — surfaced to the UI, not raised
            result["generation_error"] = str(exc)
    return result
