"""Route ②: Product editor — create and edit, with validation and an audit trail."""

import streamlit as st

from lib.atlas_client import CATEGORIES, PRODUCT_TYPES, STATUSES, TYPE_LABELS
from lib.catalog import (business_view, get_product, list_products,
                         next_product_id, recent_events, save_product,
                         validate_product)
from lib.ui import (connection_guard, page_header, query_panel, seed_guard,
                    story_arc, synthetic_note)

st.set_page_config(page_title="Product Catalog Studio · Product editor",
                   page_icon="②", layout="wide")
connection_guard()
seed_guard()

page_header("②", "Product editor",
            "Add a product or change one, and watch the type-specific fields "
            "follow the product type you chose.")
story_arc(
    problem="A new product line arrives with attributes the catalog has never "
            "stored before, and the team cannot wait for a migration window.",
    interaction="Create or edit a product; the form's type-specific section "
                "changes with the selected product type.",
    mechanism="A single upsert writes whichever fields the document needs, and "
              "re-embeds the product so search picks it up immediately.",
    tradeoff="Validation here is application-side. Without a database validator, "
             "a different client could still write a different shape.")

existing = list_products(page_size=100)["items"]
options = ["➕ Create a new product"] + [
    f"{d['product_id']} · {d['name']}" for d in existing]
choice = st.selectbox("Product", options)

if choice.startswith("➕"):
    doc, mode = {}, "create"
    st.caption(f"New product will be stored as `{next_product_id()}`.")
else:
    doc = get_product(choice.split(" · ")[0]) or {}
    mode = "edit"

ptype_default = doc.get("product_type", "equipment")
c1, c2, c3 = st.columns(3)
ptype = c1.selectbox("Product type", PRODUCT_TYPES,
                     index=PRODUCT_TYPES.index(ptype_default),
                     format_func=lambda v: TYPE_LABELS[v])
cats = CATEGORIES[ptype]
cat_default = doc.get("category") if doc.get("category") in cats else cats[0]
category = c2.selectbox("Category", cats, index=cats.index(cat_default))
status = c3.selectbox("Availability", STATUSES,
                      index=STATUSES.index(doc.get("status", "active")))

c1, c2, c3 = st.columns(3)
name = c1.text_input("Name", value=doc.get("name", ""))
sku = c2.text_input("SKU", value=doc.get("sku", ""))
amount = c3.number_input("Price (USD)", min_value=0.0, step=10.0,
                         value=float((doc.get("price") or {}).get("amount", 0.0)))
summary = st.text_input("Summary (this is what keyword search matches)",
                        value=doc.get("summary", ""))
description = st.text_area("Description", value=doc.get("description", ""),
                           height=90)
tags = st.text_input("Tags (comma separated)",
                     value=", ".join(doc.get("tags", []) or []))

st.markdown(f"#### Fields specific to **{TYPE_LABELS[ptype]}**")
st.caption("These fields are written only onto documents of this product type.")
extra: dict = {}
if ptype == "equipment":
    specs = doc.get("specs") or {}
    e1, e2, e3, e4 = st.columns(4)
    extra["specs"] = {
        "power_source": e1.selectbox(
            "Power source", ["Mains 120V", "Mains 230V", "Battery", "Pneumatic"],
            index=0 if not specs.get("power_source") else
            ["Mains 120V", "Mains 230V", "Battery",
             "Pneumatic"].index(specs["power_source"])),
        "weight_kg": e2.number_input("Weight (kg)", min_value=0.0, step=0.5,
                                     value=float(specs.get("weight_kg", 5.0))),
        "warranty_months": e3.number_input(
            "Warranty (months)", min_value=0, step=6,
            value=int(specs.get("warranty_months", 24))),
    }
    extra["lead_time_days"] = e4.number_input(
        "Lead time (days)", min_value=0, step=1,
        value=int(doc.get("lead_time_days", 14)))
elif ptype == "consumable":
    pack, handling = doc.get("pack") or {}, doc.get("handling") or {}
    hazards = ["None", "Irritant", "Flammable", "Corrosive"]
    e1, e2, e3, e4 = st.columns(4)
    extra["pack"] = {
        "units_per_pack": e1.number_input(
            "Units per pack", min_value=1, step=1,
            value=int(pack.get("units_per_pack", 10))),
        "unit_size": e2.text_input("Unit size", value=pack.get("unit_size", "1 L")),
    }
    extra["handling"] = {
        "hazard_class": e3.selectbox(
            "Hazard class", hazards,
            index=hazards.index(handling.get("hazard_class", "None"))),
        "shelf_life_months": e4.number_input(
            "Shelf life (months)", min_value=1, step=1,
            value=int(handling.get("shelf_life_months", 24))),
        "storage": handling.get("storage", "Ambient"),
    }
else:
    coverage, term = doc.get("coverage") or {}, doc.get("term") or {}
    tiers = ["Next business day", "Same day", "4-hour", "Remote only"]
    e1, e2, e3, e4 = st.columns(4)
    extra["coverage"] = {
        "response_tier": e1.selectbox(
            "Response tier", tiers,
            index=tiers.index(coverage.get("response_tier",
                                           "Next business day"))),
        "on_site": e2.checkbox("On-site", value=bool(coverage.get("on_site"))),
        "hours": coverage.get("hours", "Business hours"),
    }
    extra["term"] = {
        "months": e3.number_input("Term (months)", min_value=1, step=1,
                                  value=int(term.get("months", 12))),
        "auto_renew": e4.checkbox("Auto-renew",
                                  value=bool(term.get("auto_renew", True))),
    }
    extra["entitlements"] = [s.strip() for s in st.text_input(
        "Entitlements (comma separated)",
        value=", ".join(doc.get("entitlements", []) or [])).split(",") if s.strip()]

payload = {
    "product_id": doc.get("product_id"),
    "name": name, "sku": sku, "product_type": ptype, "category": category,
    "status": status, "summary": summary, "description": description,
    "tags": [t.strip() for t in tags.split(",") if t.strip()],
    "price": {"amount": amount, "currency": "USD",
              "unit": {"equipment": "each", "consumable": "per pack",
                       "service_plan": "per plan"}[ptype]},
    **extra,
}

query_panel("Document that will be written", {k: v for k, v in payload.items()
                                              if v not in (None, "", [])})

errors = validate_product(payload)
if errors:
    st.warning("Validation will block this save:\n\n"
               + "\n".join(f"- {e}" for e in errors))

if st.button("💾 Save product", type="primary", use_container_width=True):
    try:
        outcome = save_product(payload)
        st.success(f"Product `{outcome['product']['product_id']}` "
                   f"{outcome['action']} and re-embedded for search.")
        if outcome["embed_error"]:
            st.warning("Stored without an embedding, so only keyword search "
                       f"will find it: {outcome['embed_error']}")
        for label, value in business_view(outcome["product"]):
            st.markdown(f"**{label}** · {value}")
    except ValueError as e:
        st.error(f"Rejected before the write: {e}")

st.markdown("---")
st.markdown("#### 🧾 Audit trail (`pcs_product_events`)")
st.caption("Every save appends one small event document — who changed what, "
           "when, and which fields were written.")
st.dataframe(recent_events(), use_container_width=True, hide_index=True)

synthetic_note()
