"""App-wide Demo Readiness page.

Checks MongoDB connectivity, seeded data, collection validators, required
indexes, Vector Search readiness, knowledge embeddings, and optional AI-key
availability — without ever revealing a secret value. Also offers one-click
seed and index creation so a presenter can get to green quickly.
"""

import streamlit as st

from lib.atlas_client import KNOWLEDGE_COLLECTION, get_db
from lib.embeddings import embedding_dim
from lib.queries import VECTOR_INDEX
from lib.readiness import run_all
from lib.ui import connection_guard, page_header, synthetic_note
from seed_data import seed as run_seed

st.set_page_config(page_title="CropTrace · Demo Readiness", page_icon="🩺",
                   layout="wide")
connection_guard()

page_header("🩺", "Demo Readiness",
            "Confirm the environment before you present. Green across the board "
            "means every route will work.")

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
        with st.spinner("Seeding synthetic plots, products, treatments, "
                        "predictions, and embedded knowledge notes…"):
            run_seed()
        st.toast("Seeded. Now create the Vector Search index.")
        st.rerun()
with c2:
    if st.button("🧭 Create Vector Search index", use_container_width=True):
        coll = get_db()[KNOWLEDGE_COLLECTION]
        try:
            existing = {ix["name"] for ix in coll.list_search_indexes()}
        except Exception:
            existing = set()
        if VECTOR_INDEX in existing:
            st.info(f"Index `{VECTOR_INDEX}` already exists.")
        else:
            coll.create_search_index({
                "name": VECTOR_INDEX, "type": "vectorSearch",
                "definition": {"fields": [
                    {"type": "vector", "path": "embedding",
                     "numDimensions": embedding_dim(), "similarity": "cosine"},
                    {"type": "filter", "path": "crop"},
                    {"type": "filter", "path": "category"},
                ]}})
            st.success(f"Requested `{VECTOR_INDEX}`. Atlas builds it "
                       "asynchronously — allow 1-2 minutes, then re-check.")
        st.rerun()

st.caption("Equivalent CLI: `python3 seed_data.py` and "
           "`python3 scripts/create_indexes.py`. Teardown: "
           "`python3 teardown.py`.")

st.markdown("---")
st.info("🔐 Secrets are never displayed. AI-key checks report only whether a "
        "key is present, and API keys are read server-side only.")
synthetic_note()
