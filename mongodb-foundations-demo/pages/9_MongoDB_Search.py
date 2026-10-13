"""Section ⑧: MongoDB Search — full-text, semantic, hybrid, and AI retrieval."""

import streamlit as st
from pymongo.errors import PyMongoError

from lib.explain import stage_notes, to_mongosh
from lib.search import (hybrid_search, keyword_search, rerank_search,
                        semantic_search)
from lib.search_config import (VECTOR_INDEX, TEXT_INDEX, namespace,
                               rerank_available)
from lib.search_data import CONTRAST_QUERIES
from lib.ui import (connection_guard, cue, page_header, page_setup,
                    presenter_mode, prose, search_data_guard,
                    search_index_guard, sidebar_reset, synthetic_note, table,
                    takeaway)

page_setup("MongoDB Search", icon="⑧")
presenter_mode()
connection_guard()
sidebar_reset()
search_data_guard()
search_index_guard()

page_header("⑧", "MongoDB Search",
            "One query, four strategies — over the same chunked corpus, on the "
            "same cluster.")

ns = namespace()
st.caption("Namespace `{database}.{collection}` · text index `{text_index}` · "
           "vector index `{vector_index}` (autoEmbed · `{embedding_model}`)."
           .format(**ns))

query = st.selectbox(
    "Query (intent-based phrasings, chosen so keyword and semantic disagree)",
    CONTRAST_QUERIES)
query = st.text_input("…or type your own", value=query)


def _run(fn):
    try:
        return fn(query), None
    except PyMongoError as exc:
        return None, str(exc)
    except RuntimeError as exc:  # optional-dependency / key guards
        return None, str(exc)


def _show(results, pipeline, *, reproducible=True):
    st.success("{} result(s).".format(len(results)))
    table(results, "No matches.")
    if reproducible:
        st.markdown("**The exact aggregation — paste into `mongosh`:**")
        st.code(to_mongosh(pipeline), language="javascript")
        with st.expander("What each stage does"):
            for op, note in stage_notes(pipeline):
                st.markdown("- `{}` — {}".format(op, note))


fts, semantic, hybrid, ai = st.tabs(
    ["Full-text (BM25)", "Semantic (autoEmbed)", "Hybrid (RRF)",
     "AI retrieval (rerank)"])

with fts:
    st.markdown("#### Atlas Search — literal word matching")
    st.caption("Index `{}`. Fast, exact, and blind to synonyms and paraphrase."
               .format(TEXT_INDEX))
    if st.button("▶︎ Run full-text search", key="run_fts", type="primary"):
        out, err = _run(keyword_search)
        if err:
            st.error("Search failed: {}".format(err))
        else:
            _show(*out)
    st.caption("SQL/relational intent · a `LIKE`/inverted-index keyword lookup, "
               "ranked by BM25 term frequency.")

with semantic:
    st.markdown("#### Atlas Vector Search — meaning, not words")
    st.caption("Index `{}`. Atlas embeds your query text server-side with the "
               "autoEmbed model — no vector is computed in this app."
               .format(VECTOR_INDEX))
    if st.button("▶︎ Run semantic search", key="run_sem", type="primary"):
        out, err = _run(semantic_search)
        if err:
            st.error("Search failed: {}".format(err))
        else:
            _show(*out)
    cue("Same query, different hits. Semantic search retrieves passages that "
        "share intent even when they share almost no words.")

with hybrid:
    st.markdown("#### `$rankFusion` — the best of both")
    st.caption("Runs the keyword and semantic legs, ranks each, then fuses the "
               "ranks (RRF). Requires MongoDB 8.1+.")
    if st.button("▶︎ Run hybrid search", key="run_hyb", type="primary"):
        out, err = _run(hybrid_search)
        if err:
            st.error("Search failed: {}".format(err))
        else:
            _show(*out)

with ai:
    st.markdown("#### AI retrieval — hybrid, then a cross-encoder reranker")
    st.caption("Hybrid fetches a wide candidate set; a Voyage AI reranker "
               "re-scores each candidate against the query. This final step "
               "runs client-side and is the one strategy mongosh cannot "
               "reproduce.")
    if not rerank_available():
        st.info("**Reranking is optional and not configured.** Set "
                "`VOYAGE_API_KEY` in `.env` to enable it. The other three "
                "strategies need no key.")
    elif st.button("▶︎ Run AI retrieval", key="run_ai", type="primary"):
        out, err = _run(rerank_search)
        if err:
            st.error("Rerank failed: {}".format(err))
        else:
            results, pipeline = out
            st.success("{} result(s). Compare `hybrid_rank` to `rerank_rank` "
                       "to see how far the reranker moved each hit."
                       .format(len(results)))
            table(results, "No matches.")
            st.markdown("**The hybrid retrieval that feeds the reranker:**")
            st.code(to_mongosh(pipeline), language="javascript")

prose(
    "**Why this matters for a relational audience.** Full-text search is the "
    "familiar inverted index: precise when the user knows the words, blind when "
    "they do not. Vector search indexes *meaning*, so a paraphrase still "
    "retrieves the right passage. Hybrid fusion keeps the precision of keywords "
    "and the recall of vectors in one query, and reranking adds a final, "
    "query-aware sort. All four read the same `text` field on the same "
    "collection — the comparison is honest.\n\n"
    "**Automated Embedding** is the operational point: the vector index is "
    "declared as `autoEmbed`, so Atlas generates embeddings at index time and "
    "at query time. There is no embedding service to run, no vector to store by "
    "hand, and no drift between the two.")

takeaway("Keyword for precision, vector for meaning, hybrid for both, rerank "
         "for the final say — one collection, one query text, four strategies.")

synthetic_note()
