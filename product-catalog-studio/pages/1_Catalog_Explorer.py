"""Route ①: Catalog explorer — filter, sort, and page one collection."""

import streamlit as st

from lib.atlas_client import (ALL_CATEGORIES, CATEGORIES, PRODUCT_TYPES,
                              STATUSES, TYPE_LABELS)
from lib.catalog import (PAGE_SIZE, SORT_OPTIONS, business_view,
                         distinct_field_paths, list_products, price_bounds,
                         type_attribute_options)
from lib.ui import (connection_guard, page_header, product_card, query_panel,
                    seed_guard, story_arc, synthetic_note)

st.set_page_config(page_title="Product Catalog Studio · Catalog explorer",
                   page_icon="①", layout="wide")
connection_guard()
seed_guard()

page_header("①", "Catalog explorer",
            "Instruments, consumables, and service plans in one collection — "
            "each keeping the attributes that actually describe it.")
story_arc(
    problem="Three product lines describe themselves differently, so a single "
            "fixed table would be mostly empty columns.",
    interaction="Filter by type, category, availability, price, and the one "
                "attribute that only exists on the selected type.",
    mechanism="One collection of documents with varying shapes; filters and "
              "sorts are plain query documents served by btree indexes.",
    tradeoff="Nothing enforces the shape at the database level here — the rules "
             "live in the application, which is a deliberate choice to discuss.")

lo, hi = price_bounds()

st.sidebar.markdown("### Filters")
ptype = st.sidebar.selectbox("Product type", [None] + PRODUCT_TYPES,
                             format_func=lambda v: "All types" if v is None
                             else TYPE_LABELS[v])
categories = CATEGORIES[ptype] if ptype else ALL_CATEGORIES
category = st.sidebar.selectbox("Category", [None] + categories,
                                format_func=lambda v: v or "All categories")
status = st.sidebar.selectbox("Availability", [None] + STATUSES,
                             format_func=lambda v: (v or "any").title())
price_range = st.sidebar.slider("Price (USD)", min_value=float(lo),
                                max_value=float(hi), value=(float(lo), float(hi)))
attr_label, attr_options = type_attribute_options(ptype)
attr_value = None
if attr_options:
    attr_value = st.sidebar.selectbox(attr_label, [None] + attr_options,
                                      format_func=lambda v: v or f"Any {attr_label.lower()}")
else:
    st.sidebar.caption("Pick a product type to filter on its type-specific "
                       "attribute.")
sort = st.sidebar.selectbox("Sort by", list(SORT_OPTIONS))

filters = {"product_type": ptype, "category": category, "status": status,
           "price_min": price_range[0], "price_max": price_range[1],
           "type_attribute": attr_value}

if "explorer_page" not in st.session_state:
    st.session_state.explorer_page = 1
signature = str(filters) + sort
if st.session_state.get("explorer_signature") != signature:
    st.session_state.explorer_signature = signature
    st.session_state.explorer_page = 1

result = list_products(filters, sort=sort, page=st.session_state.explorer_page,
                       page_size=PAGE_SIZE)

m1, m2, m3 = st.columns(3)
m1.metric("Matching products", f"{result['total']:,}")
m2.metric("Page", f"{result['page']} of {result['pages']}")
m3.metric("Filter clauses", len(result["query"]))

query_panel("Query sent to MongoDB",
            {"find": result["query"],
             "sort": [[f, d] for f, d in SORT_OPTIONS[sort]],
             "skip": (result["page"] - 1) * result["page_size"],
             "limit": result["page_size"]})

if not result["items"]:
    st.warning("No products match these filters. Widen the price range or clear "
               "a filter.")
else:
    cols = st.columns(3)
    for i, doc in enumerate(result["items"]):
        with cols[i % 3]:
            with st.container(border=True):
                product_card(doc)
                with st.expander("Business view"):
                    for label, value in business_view(doc):
                        st.markdown(f"**{label}** · {value}")
                with st.expander("Stored document"):
                    st.json(doc, expanded=False)

nav1, nav2, _ = st.columns([1, 1, 6])
if nav1.button("← Previous", disabled=result["page"] <= 1,
               use_container_width=True):
    st.session_state.explorer_page -= 1
    st.rerun()
if nav2.button("Next →", disabled=result["page"] >= result["pages"],
               use_container_width=True):
    st.session_state.explorer_page += 1
    st.rerun()

st.markdown("---")
with st.expander("🧬 Fields present per product type (read from the data)"):
    st.caption("Read from the stored documents, not from a declared schema — "
               "this is the variation the document model is absorbing.")
    shapes = distinct_field_paths()
    shared = set.intersection(*(set(v) for v in shapes.values())) if shapes else set()
    for ptype_name, fields in shapes.items():
        unique = [f for f in fields if f not in shared]
        st.markdown(f"**{TYPE_LABELS.get(ptype_name, ptype_name)}** — unique to "
                    f"this type: `{'`, `'.join(unique) or '—'}`")
    st.caption(f"Shared by every type: `{'`, `'.join(sorted(shared))}`")

synthetic_note()
