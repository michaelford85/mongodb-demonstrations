"""Route ④: Discovery checklist — what to ask after the demo."""

import streamlit as st

from lib.catalog import catalog_stats
from lib.ui import (connection_guard, page_header, seed_guard, story_arc,
                    synthetic_note)

st.set_page_config(page_title="Product Catalog Studio · Discovery checklist",
                   page_icon="④", layout="wide")
connection_guard()
seed_guard()

page_header("④", "Discovery checklist",
            "Close the session by turning what was just shown into the next "
            "set of questions.")
story_arc(
    problem="A demo proves a mechanism; it does not prove a fit for someone "
            "else's catalog.",
    interaction="Walk the checklist together and capture answers live.",
    mechanism="Each question maps to a specific capability shown in routes ① to "
              "③, so the follow-up is concrete.",
    tradeoff="Some answers will point away from this design — that is the point "
             "of asking before proposing.")

stats = catalog_stats()
m1, m2, m3, m4 = st.columns(4)
m1.metric("Products in the demo", stats["total"])
m2.metric("Product types", len([v for v in stats["by_type"].values() if v]))
m3.metric("With embeddings", stats["embedded"])
m4.metric("Audit events", stats["events"])
st.caption("Scale disclosure: this is an 18-product synthetic catalog. Nothing "
           "here evidences behaviour at production volume.")

st.markdown("---")
st.markdown("### What routes ① to ③ actually demonstrated")
st.markdown(
    "1. **One collection held three product shapes.** Equipment, consumable, and "
    "service-plan documents carry different attributes with no unused columns "
    "and no side tables.\n"
    "2. **A new product line needed no migration.** The editor wrote a new "
    "document shape with a single upsert, and the product was searchable "
    "immediately.\n"
    "3. **Keyword, vector, and hybrid search ran on the same data.** No separate "
    "search cluster, no synchronisation pipeline, and the same structured "
    "filters applied to every mode.")

st.markdown("---")
st.markdown("### Discovery questions")
QUESTIONS = [
    ("Catalog shape",
     ["How many product lines do you sell, and how differently do they describe "
      "themselves?",
      "How often does a new attribute or product line appear?",
      "What does adding an attribute cost you today, in time and in downtime?"]),
    ("Search behaviour",
     ["How do shoppers actually phrase requests — SKUs, part numbers, or "
      "descriptions of an outcome?",
      "What fraction of searches return nothing useful today?",
      "Who owns relevance tuning, and how is it measured?"]),
    ("Systems in the path",
     ["Which system is the source of truth for product data today?",
      "Is there a separate search index, and what keeps it in sync?",
      "Where do pricing, stock, and entitlements actually live?"]),
    ("Governance and scale",
     ["Which fields must be enforced at the database level rather than in the "
      "application?",
      "What are the catalog size, read volume, and peak search rate?",
      "What are the requirements for auditing catalog changes?"]),
    ("AI and embeddings",
     ["Is there an approved embedding provider, and can data leave the "
      "environment?",
      "Would a re-embedding pass on the full catalog be acceptable, and how often?",
      "Is a generated summary acceptable to shoppers, and who reviews it?"]),
]
for heading, items in QUESTIONS:
    with st.container(border=True):
        st.markdown(f"**{heading}**")
        for q in items:
            st.checkbox(q, key=f"chk_{heading}_{q[:24]}")

st.markdown("---")
st.markdown("### Where this design is the wrong answer")
st.markdown(
    "- The catalog is genuinely uniform, and a single well-normalised table "
    "already describes every product with no sparse columns.\n"
    "- Referential integrity must be enforced by the database across many "
    "entities, and application-level rules are not acceptable.\n"
    "- Reporting is dominated by ad-hoc SQL across heavily normalised tables, "
    "and the analytics tooling assumes that shape.\n"
    "- Relevance requirements are severe enough to justify a dedicated search "
    "platform and a team to tune it.\n\n"
    "In those cases the honest recommendation is to keep the relational core and "
    "revisit only the parts that hurt.")

st.markdown("---")
st.markdown("### Honest limits of this demonstration")
st.markdown(
    f"- **Fictional data.** Kestrel Labworks and all {stats['total']} products "
    "were invented for this session.\n"
    "- **Default embeddings are a local deterministic model**, chosen so the demo "
    "runs with no API keys. It shows the mechanics of vector search, not "
    "production relevance.\n"
    "- **No performance claim.** No load test, no sizing exercise, and no "
    "latency measurement was performed.\n"
    "- **No database-level schema governance.** Validation lives in the "
    "application here; a real deployment would add `$jsonSchema` validators.")

synthetic_note()
