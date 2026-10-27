#!/usr/bin/env python3
"""Streamlit UI: semantic search over the CDC-fed Atlas read model.

Run:  streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from common import atlas_collection, load_config, voyage_embed  # noqa: E402

st.set_page_config(page_title="CDC Vector Search Demo", page_icon="🔎", layout="wide")


@st.cache_resource
def get_collection():
    cfg = load_config()
    return cfg, atlas_collection(cfg)


def vector_search(collection, embedding, entity_type: str | None, limit: int):
    pipeline = [
        {
            "$vectorSearch": {
                "index": "search_items_vector",
                "path": "embedding",
                "queryVector": embedding,
                "numCandidates": max(limit * 20, 100),
                "limit": limit,
                **({"filter": {"entity_type": entity_type}} if entity_type else {}),
            }
        },
        {"$project": {
            "score": {"$meta": "vectorSearchScore"},
            "title": 1,
            "body": 1,
            "tags": 1,
            "department": 1,
            "entity_type": 1,
            "source_id": 1,
            "source_updated_at": 1,
            "cdc_operation": 1,
            "processed_at": 1,
        }},
    ]
    return list(collection.aggregate(pipeline))


def main() -> None:
    cfg, collection = get_collection()

    st.title("🔎 CDC → Atlas Vector Search")
    st.caption(
        f"Read model `{cfg['database']}.{cfg['collection']}` — fed continuously from "
        "PostgreSQL via AWS DMS CDC → MSK → Atlas Stream Processing. "
        f"Embeddings: {cfg['voyage_model']} ({cfg['voyage_dimensions']} dims)."
    )

    query = st.text_input(
        "Query",
        placeholder="e.g. how do I get my laptop replaced?",
    )
    entity_type = st.selectbox(
        "Entity type filter",
        ["(all)", "article", "faq"],
        index=0,
    )
    limit = st.slider("Max results", 5, 25, 10)

    if not query:
        st.info("Enter a query to search the read model.")
        return

    embedding = voyage_embed(cfg, [query], input_type="query")[0]
    if len(embedding) != cfg["voyage_dimensions"]:
        st.error(
            f"Query embedding has {len(embedding)} dims but the index expects "
            f"{cfg['voyage_dimensions']}. Align VOYAGE_DIMENSIONS with the index."
        )
        return

    results = vector_search(
        collection,
        embedding,
        None if entity_type == "(all)" else entity_type,
        limit,
    )

    st.caption(
        f"{len(results)} result(s) — freshness: the newest document in this "
        f"result set was ingested at "
        f"{max((r.get('processed_at') for r in results), default=None)}."
    )
    for r in results:
        with st.container(border=True):
            cols = st.columns([4, 1])
            cols[0].markdown(f"**{r.get('title', '(untitled)')}**")
            cols[1].metric("score", f"{r.get('score', 0):.4f}")
            st.write(r.get("body", ""))
            st.caption(
                f"type={r.get('entity_type')} · dept={r.get('department')} · "
                f"tags={r.get('tags')} · source_id={r.get('source_id')} · "
                f"cdc_op={r.get('cdc_operation')} · updated={r.get('source_updated_at')}"
            )


if __name__ == "__main__":
    main()
