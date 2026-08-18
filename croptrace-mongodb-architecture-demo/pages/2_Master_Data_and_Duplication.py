"""Route ②: Master data & controlled duplication."""

import pandas as pd
import streamlit as st

from lib.atlas_client import PRODUCT_IDS
from lib.master_data import (get_product, resolve_treatments_for_product,
                             snapshot_vs_reference_note, update_product_guidance)
from lib.sample_data import build_products
from lib.ui import (badge, connection_guard, db, page_header, presenter_notes,
                    seed_guard, story_arc, synthetic_note)

st.set_page_config(page_title="CropTrace · Master data & duplication",
                   page_icon="②", layout="wide")
connection_guard()
seed_guard()
database = db()

page_header("②", "Master data & controlled duplication",
            "A tiny display snapshot on each treatment, plus a live reference "
            "to the authoritative product record.")
story_arc(
    problem="Product labels and restriction guidance change often, but a "
            "treatment must also record what was true when it was applied.",
    interaction="Change an authoritative product's status/guidance, then watch "
                "which treatment fields move and which stay frozen.",
    mechanism="A small `product_snapshot` for history + a `product_ref` that "
              "resolves live from `crop_protection_products`.",
    tradeoff="If strict referential integrity across records is a hard "
             "requirement, relational foreign keys enforce it automatically; "
             "here it is a modelled design decision.")

presenter_notes(
    talk_track="Every treatment keeps a small snapshot of the product — its "
               "label and category at application time — for history and "
               "display. But status and restriction guidance change often, so "
               "those are resolved live from the one authoritative product "
               "record instead of being copied everywhere. Watch: I change the "
               "product once, and every treatment's resolved guidance updates, "
               "while the historical snapshot stays exactly as applied.",
    click_path=["Pick a product", "Note its current version/status",
                "Edit status + guidance and save",
                "See version bump on the authoritative record",
                "See resolved fields change while snapshots stay frozen"],
    takeaway="Targeted denormalization: snapshot only what must be historical; "
             "reference the single source of truth for what changes.",
    caveat="MongoDB does not auto-cascade this like a relational FK — it is a "
           "deliberate model. If you need enforced referential integrity, that "
           "is a point in favour of a relational design.")

note = snapshot_vs_reference_note()
product_id = st.selectbox("Authoritative product", PRODUCT_IDS)
product = get_product(database, product_id)

c1, c2, c3 = st.columns(3)
c1.metric("Version", product.get("version"))
c2.metric("Status", product.get("status"))
c3.metric("PHI (days)", product.get("phi_days"))
st.caption(f"**{product.get('label_name')}** · {product.get('category')}")
st.info(f"Current guidance: {product.get('restriction_guidance')}")

st.markdown("#### ✍️ Change the authoritative record")
with st.form("update_product"):
    new_status = st.selectbox("New status", ["active", "restricted", "withdrawn"],
                              index=["active", "restricted", "withdrawn"].index(
                                  product.get("status", "active")))
    new_guidance = st.text_input("New restriction guidance",
                                 value=product.get("restriction_guidance", ""))
    submitted = st.form_submit_button("Save to authoritative record",
                                      type="primary")
if submitted:
    updated = update_product_guidance(database, product_id, status=new_status,
                                      restriction_guidance=new_guidance)
    st.success(f"Updated `{product_id}` → version {updated['version']}. "
               "Only the master record changed.")
    st.rerun()

st.markdown("---")
st.markdown("#### 🔍 Snapshot (frozen) vs resolved (live) per treatment")
rows = resolve_treatments_for_product(database, product_id)
if not rows:
    st.caption("No treatments reference this product.")
else:
    table = []
    for r in rows:
        table.append({
            "treatment_id": r["treatment_id"], "plot_id": r["plot_id"],
            "snapshot.label_name": r["snapshot"].get("label_name"),
            "snapshot.version": r["snapshot"].get("snapshot_version"),
            "resolved.status": r["resolved"].get("status"),
            "resolved.version": r["resolved"].get("version"),
            "resolved.guidance": r["resolved"].get("restriction_guidance"),
        })
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)

st.markdown("#### 🧭 Design decision")
st.markdown("Historical snapshot fields: "
            + " ".join(badge(f, "#6b7280") for f in note["snapshot_fields"]),
            unsafe_allow_html=True)
st.markdown("Resolved-from-authoritative fields: "
            + " ".join(badge(f, "#2563eb") for f in note["resolved_fields"]),
            unsafe_allow_html=True)
st.warning(note["why"] + " This is a design choice, **not** automatic "
           "referential integrity.")

st.markdown("---")
if st.button("🔄 Reset demo (restore products to seeded state)"):
    for p in build_products():
        database.crop_protection_products.replace_one(
            {"product_id": p["product_id"]}, p, upsert=True)
    st.toast("Products restored to their seeded values.")
    st.rerun()
synthetic_note()
