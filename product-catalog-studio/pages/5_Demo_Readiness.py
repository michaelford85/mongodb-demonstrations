"""App-wide Demo Readiness page.

Checks MongoDB connectivity, seeded catalog, required btree indexes, both Atlas
search indexes, product embeddings, and optional AI-key availability — without
ever revealing a secret value. Also offers one-click seed and index creation so
a presenter can get to green quickly.
"""

import streamlit as st

from lib.atlas_client import products
from lib.embeddings import embedding_dim, provider_name
from lib.readiness import run_all
from lib.search import (TEXT_INDEX, VECTOR_INDEX, text_index_definition,
                        vector_index_definition)
from lib.ui import connection_guard, page_header, synthetic_note
from seed_data import seed as run_seed

st.set_page_config(page_title="Product Catalog Studio · Demo Readiness",
                   page_icon="🩺", layout="wide")
connection_guard()

page_header("🩺", "Demo Readiness",
            "Environment checks for this demo. Green across the board means "
            "every route will work.")

checks = run_all()
all_ok = all(c["ok"] for c in checks)
if all_ok:
    st.success("All readiness checks passed. Every route is ready to demo.")
else:
    st.warning("Some checks need attention. Follow the fix hints below.")

for c in checks:
    icon = "✅" if c["ok"] else "⚠️"
    with st.container(border=True):
        st.markdown(f"{icon} **{c['name']}** — {c['detail']}")
        if not c["ok"] and c["fix"]:
            st.caption(f"→ {c['fix']}")

st.markdown("---")
st.markdown("#### 🚀 One-click setup")
c1, c2 = st.columns(2)
with c1:
    if st.button("🌱 Seed demo data", use_container_width=True):
        with st.spinner("Seeding the synthetic catalog and embedding every "
                        "product…"):
            run_seed()
        st.toast("Seeded. Now create the search indexes.")
        st.rerun()
with c2:
    if st.button("🧭 Create search indexes", use_container_width=True):
        coll = products()
        try:
            existing = {ix["name"]: ix for ix in coll.list_search_indexes()}
        except Exception:
            existing = {}
        changed = []
        for definition in (text_index_definition(), vector_index_definition()):
            name = definition["name"]
            current = existing.get(name)
            if current is None:
                coll.create_search_index(definition)
                changed.append(name)
            elif current.get("latestDefinition") != definition["definition"]:
                coll.update_search_index(name, definition["definition"])
                changed.append(name)
        if changed:
            st.success(f"Requested {changed}. Atlas builds search indexes "
                       "asynchronously — allow 1-2 minutes, then re-check.")
        else:
            st.info("Both search indexes already match the current definition.")
        st.rerun()

st.caption("Equivalent CLI: `python3 seed_data.py` and "
           "`python3 scripts/create_indexes.py`. Status: "
           "`python3 scripts/status.py`. Teardown: `python3 teardown.py`.")

st.markdown("---")
st.markdown("#### ⚙️ Active configuration")
st.markdown(f"- Embedding provider: `{provider_name()}` · {embedding_dim()} "
            "dimensions\n"
            f"- Atlas Search index: `{TEXT_INDEX}`\n"
            f"- Vector Search index: `{VECTOR_INDEX}`")
st.caption("The vector dimension must match between `EMBEDDING_DIM`, the seeded "
           "vectors, and the vector index. Changing provider means re-seeding and "
           "re-creating the vector index.")

st.markdown("---")
st.info("🔐 Secrets are never displayed. AI-key checks report only whether a key "
        "is present, and API keys are read server-side only.")
synthetic_note()
