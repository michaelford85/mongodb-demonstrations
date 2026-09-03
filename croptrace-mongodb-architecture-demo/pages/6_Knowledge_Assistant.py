"""Route ⑥: AI exploration — Voyage + Atlas Vector Search + Claude."""

import streamlit as st

from lib.ai import ask, claude_available, DEFAULT_MODEL
from lib.atlas_client import knowledge_has_embeddings
from lib.embeddings import provider_name
from lib.readiness import check_vector_index
from lib.ui import (badge, connection_guard, db, page_header, presenter_notes,
                    seed_guard, story_arc, synthetic_note)

st.set_page_config(page_title="CropTrace · Knowledge Assistant",
                   page_icon="⑥", layout="wide")
connection_guard()
seed_guard()
database = db()

page_header("⑥", "AI: Voyage + Atlas Vector Search + Claude",
            "A retrieval-first knowledge assistant grounded only on the "
            "synthetic demo corpus. Optional and independently runnable.")
story_arc(
    problem="Growers ask free-text questions; guidance lives in unstructured "
            "notes that keyword search handles poorly.",
    interaction="Ask a question; see retrieved sources first, then a grounded "
                "answer built only from them.",
    mechanism="Embeddings → Atlas Vector Search retrieval → the retrieved "
              "context plus the question are passed to Claude.",
    tradeoff="This fosters a discussion; it is not a committed roadmap. Without "
             "keys it still demonstrates vector retrieval.")

presenter_notes(
    talk_track="This is an exploration, not a roadmap. It's retrieval-first: I "
               "embed the question, run Atlas Vector Search over a small "
               "synthetic corpus, and show the sources before any answer. Only "
               "those retrieved snippets plus the question go to Claude, so the "
               "answer is grounded in the displayed demo corpus. With no API "
               "keys, retrieval still runs on the local embedder and the answer "
               "degrades to a clearly-labelled extractive summary.",
    click_path=["Confirm the vector index status",
                "Type a grower question", "Run the assistant",
                "Read the retrieved sources first",
                "Read the grounded answer and its mode label"],
    takeaway="Retrieval-grounded generation over Atlas Vector Search, with keys "
             "read server-side only.",
    caveat="Vector search adds real value for semantic recall; for purely "
           "structured lookups, a plain index or SQL query is simpler.")

# ── Configuration / status strip ────────────────────────────────────────────
vindex = check_vector_index()
c1, c2, c3 = st.columns(3)
c1.markdown("**Embedding provider**  \n" + badge(provider_name(), "#2563eb"),
            unsafe_allow_html=True)
c2.markdown("**Vector index**  \n"
            + badge(vindex["detail"], "#059669" if vindex["ok"] else "#d97706"),
            unsafe_allow_html=True)
mode = ("Claude ready" if claude_available() else "No-keys mode (extractive)")
c3.markdown("**Answer mode**  \n"
            + badge(mode, "#7c3aed" if claude_available() else "#6b7280"),
            unsafe_allow_html=True)

if not knowledge_has_embeddings():
    st.warning("Knowledge notes have no embeddings yet. Run `python3 "
               "seed_data.py`, then `python3 scripts/create_indexes.py`.")
    st.stop()
if not vindex["ok"]:
    st.info("Vector index is not queryable yet — the assistant falls back to "
            "an in-app cosine scan so you can still demo retrieval. "
            f"({vindex['detail']}) {vindex['fix']}")
if not claude_available():
    st.info("**No-keys mode.** `ANTHROPIC_API_KEY` is not set, so answers are "
            "extractive summaries of the retrieved snippets — never free-form "
            "model output. Set the key server-side to enable Claude "
            f"(`ANTHROPIC_MODEL` defaults to `{DEFAULT_MODEL}`).")

question = st.text_input(
    "Ask a grower question",
    placeholder="e.g. how do I keep residue low on strawberries near harvest?")
if st.button("🔎 Run the assistant", type="primary") and question.strip():
    with st.spinner("Retrieving from the synthetic corpus…"):
        result = ask(database, question.strip(), limit=4)

    st.markdown("#### 📚 Retrieved sources (shown before the answer)")
    st.caption(f"Retrieval path: `{result['path']}` · provider "
               f"`{result['provider']}`. The answer is grounded **only** in "
               "these displayed demo snippets.")
    for s in result["sources"]:
        with st.container(border=True):
            st.markdown(f"**[{s.get('note_id')}] {s.get('title')}** "
                        + badge(s.get("crop", ""), "#059669")
                        + " " + badge(s.get("category", ""), "#7c3aed"),
                        unsafe_allow_html=True)
            st.write(s.get("body", ""))
            if s.get("score") is not None:
                st.caption(f"similarity score: {s['score']}")

    st.markdown("#### 💬 Grounded answer")
    label = (f"Claude · {result.get('model')}" if result["mode"] == "claude"
             else "Extractive (no-keys mode)")
    st.markdown(badge(label, "#7c3aed" if result["mode"] == "claude"
                      else "#6b7280"), unsafe_allow_html=True)
    st.write(result["answer"])
    if result.get("error"):
        st.caption(f"(Claude call failed, fell back to extractive: "
                   f"{result['error']})")
    st.success("Answer grounded only in the displayed synthetic demo corpus.")

st.markdown("---")
if st.button("🔄 Reset demo (read-only route — clear the question)"):
    st.rerun()
synthetic_note()
