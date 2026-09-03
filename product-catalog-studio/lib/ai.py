"""Optional grounded summary of a retrieved product shortlist.

Retrieval always runs first (see `lib/search.py`). Only the documents that Atlas
returned are passed to Claude, and the key is read server-side only. With no
ANTHROPIC_API_KEY the workspace still shows a clearly-labelled extractive
summary assembled solely from the retrieved product fields — never a free-form
model answer, and never an invented product.
"""

from __future__ import annotations

import os

DEFAULT_MODEL = "claude-haiku-4-5"  # Anthropic's current lowest-cost model


def claude_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _line(doc: dict) -> str:
    price = doc.get("price") or {}
    return (f"[{doc.get('product_id')}] {doc.get('name')} · "
            f"type={doc.get('product_type')} · category={doc.get('category')} · "
            f"status={doc.get('status')} · "
            f"price={price.get('amount')} {price.get('currency')} "
            f"{price.get('unit', '')}\n{doc.get('summary', '')}")


def _context_block(results: list[dict]) -> str:
    return "\n\n".join(_line(d) for d in results)


def _extractive_summary(question: str, results: list[dict]) -> str:
    """Summary built only by quoting stored fields of the retrieved products."""
    if not results:
        return ("Nothing was retrieved for that request, so there is no "
                "shortlist to summarise.")
    lead = results[0]
    price = (lead.get("price") or {}).get("amount")
    rest = ", ".join(f"{d.get('name')} ({d.get('product_id')})"
                     for d in results[1:])
    text = (f"The top match for “{question}” is **{lead.get('name')}** "
            f"({lead.get('product_id')}), a {lead.get('category')} "
            f"{(lead.get('product_type') or '').replace('_', ' ')} listed as "
            f"{lead.get('status')}"
            + (f" at {price:,.2f} {(lead.get('price') or {}).get('currency')}"
               if price is not None else "")
            + f". Stored summary: {lead.get('summary', '—')}")
    if rest:
        text += f" Also shortlisted: {rest}."
    return text


def summarize_shortlist(question: str, results: list[dict]) -> dict:
    """Return {mode, model, summary} for the retrieved shortlist.

    ``mode`` is ``claude`` only when a key is present and the call succeeded;
    otherwise ``extractive``, so the UI can label the source honestly.
    """
    if not claude_available():
        return {"mode": "extractive", "model": None,
                "summary": _extractive_summary(question, results)}
    try:
        import anthropic

        model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        prompt = (
            "You help a sales engineer explain a product shortlist from a "
            "fictional catalog. Use ONLY the numbered products below. Never "
            "invent a product, price, or specification, and never mention any "
            "real company. If the shortlist does not answer the request, say "
            "so plainly. Reply in at most four sentences.\n\n"
            f"Shortlist:\n{_context_block(results)}\n\n"
            f"Shopper request: {question}")
        msg = client.messages.create(
            model=model, max_tokens=350,
            messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if b.type == "text")
        return {"mode": "claude", "model": model, "summary": text}
    except Exception as e:  # noqa: BLE001 — degrade gracefully in a live demo
        return {"mode": "extractive", "model": None,
                "summary": _extractive_summary(question, results),
                "error": str(e)}
