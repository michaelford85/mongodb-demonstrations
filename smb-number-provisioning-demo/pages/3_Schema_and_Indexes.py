"""③ Schema & indexes — readable JSON examples and the exact demo scope."""

import json

import streamlit as st

from lib.cap_service import CAP_TYPE, DEFAULT_CAP
from lib.config import collections, db_name, execution_mode, get_client
from lib.ui import connection_guard, demo_scope_note, synthetic_note

st.set_page_config(page_title="Schema & indexes · SMB provisioning demo",
                   page_icon="🗂️", layout="wide")
connection_guard()

st.markdown("# ③ Schema & indexes")
st.caption("Readable examples for the two confirmed shapes plus the "
           "demo/design recommendations. Confirmed behaviors are marked "
           "✅; demo additions are marked 🔶.")
synthetic_note()
demo_scope_note()

st.success(f"**Inspect in your database console:** database `{db_name()}` — "
           + " · ".join(f"`{c}`" for c in collections().values())
           + f". Write path on this deployment: **{execution_mode(get_client())}**.")


def json_block(title: str, doc: dict, label: str) -> None:
    st.markdown(f"#### {title} {label}")
    st.code(json.dumps(doc, indent=2, default=str), language="javascript")


json_block("`accounts` — one account record", {
    "accountId": "ACC-SMB-0001",            # ✅ unique index on accountId
    "parentAccount": "ACC-ENT-0042",        # ✅ optional hierarchy
    "superAccount": "ACC-ENT-0001",         # ✅ optional hierarchy
    "name": "Bright Harbor Dental",         # synthetic
    "featureData": {"brandedCalling": True, "logoRef": "synthetic-logo-1"},
    "serviceData": {"servicePackage": {     # ✅ attached by accountId
        "packageId": "PKG-SMB-100", "capType": CAP_TYPE, "cap": DEFAULT_CAP}},
    "billing": {"tier": "smb_trial", "currency": "USD", "synthetic": True},
    "vetting": {"status": "not_verified_demo_only"},
}, "✅ confirmed shape · 🔶 synthetic values")
st.caption("✅ The account supplies/registers its own numbers; telephone "
           "numbers are **not** embedded as an unbounded array here — each "
           "is its own `numberAssets` document.")

json_block("`numberAssets` — one telephone-number asset per document", {
    "accountId": "ACC-SMB-0001",            # ✅
    "parentAccountId": "ACC-ENT-0042",      # ✅ optional
    "superAccountId": "ACC-ENT-0001",       # ✅ optional
    "type": "local",                        # ✅
    "state": "active",                      # ✅
    "tn": {"orig": {"start": "+15555550100",  # ✅ tn.orig subdocument
                    "count": 1, "startTn": "+15555550100",
                    "endTn": "+15555550100"}},
    "callerProfileId": "cp-seed000",        # ✅ representative
    "partnerData": {"synthetic": True},     # ✅ partner-interaction data
    "vetting": {"status": "not_verified_demo_only"},  # ✅ conceptual only
    "channel": "portal",                    # 🔶 demo addition
    "idempotencyKey": "idem-…",             # 🔶 demo addition (safe retries)
    "note": "synthetic demo data",          # 🔶 demo addition
}, "✅ confirmed shape · 🔶 demo additions")
st.markdown("**Unique compound index (✅ confirmed behavior, preserved):**")
st.code("{ accountId: 1, 'tn.orig.startTn': 1, type: 1 } , { unique: true }",
        language="javascript")

json_block("`provisioningCounters` — shared counter per account", {
    "accountId": "ACC-SMB-0001", "capType": CAP_TYPE,
    "activeCount": 3, "cap": DEFAULT_CAP, "updatedAt": "…",
}, "🔶 demo/design recommendation — not a confirmed pre-existing collection")
st.markdown("**Recommended unique index:** "
            "`{ accountId: 1, capType: 1 }, { unique: true }`")

json_block("`provisioningAudit` — minimal audit event", {
    "event": "PROVISIONING_REJECTED", "accountId": "ACC-SMB-0001",
    "capType": CAP_TYPE, "requestedCount": 1,
    "resultCode": "422 SERVICE_PACKAGE_CAP_EXCEEDED", "channel": "direct_api",
    "idempotencyKey": "idem-…", "at": "…", "note": "synthetic demo data",
}, "🔶 demo/design recommendation")

st.markdown("### Cap-counting states — one configurable business rule")
st.markdown("The exact set of number states that count toward the cap lives "
            "in **one** function, `states_counting_toward_cap()` in "
            "`lib/cap_service.py`. Currently: `{'active'}`. States like "
            "`released` or `removed` do **not** consume capacity. Do not "
            "assume every state counts as active.")

st.markdown("### Confirmed vs. proposed — at a glance")
rows = [
    ("Cap is per account record (unique `accountId`)", "✅ confirmed"),
    ("Unique asset index `{accountId, tn.orig.startTn, type}`", "✅ confirmed"),
    ("Atomic conditional counter reservation", "✅ confirmed behavior · "
     "🔶 counter document is a demo recommendation"),
    ("Over-cap → 422, rejected not queued, audited", "✅ confirmed"),
    ("Removal frees capacity immediately", "✅ confirmed"),
    ("Cap lowered below usage: keep numbers, block additions", "✅ confirmed"),
    ("`provisioningCounters` / `provisioningAudit` collections", "🔶 proposed"),
    ("`channel`, `idempotencyKey` fields on assets", "🔶 proposed"),
    ("Separate SMB cluster/silo", "⏳ open decision — see page ⑤"),
]
for what, status in rows:
    st.markdown(f"- **{what}** — {status}")
