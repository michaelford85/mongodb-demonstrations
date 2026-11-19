"""Streamlit GUI for the CSFLE vs Queryable Encryption demos.

    streamlit run app.py

Wraps the CLI scripts in scripts/ with a visual walkthrough: side-by-side
concept comparison, live status of each demo collection, and the same
apply / query / decrypt / remove actions, without ever displaying key
material. Requires the same .env setup as the scripts.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from bson.binary import Binary  # noqa: E402
from pymongo.encryption import Algorithm  # noqa: E402

from common import (  # noqa: E402
    CSFLE_COLLECTION_NAME,
    CSFLE_DB_NAME,
    CSFLE_TARGET_FIELD,
    QE_COLLECTION_NAME,
    QE_DB_NAME,
    QE_TARGET_FIELD,
    get_standard_client,
    load_settings,
)

st.set_page_config(page_title="CSFLE vs Queryable Encryption",
                   page_icon="🔐", layout="wide")


@st.cache_resource
def settings():
    return load_settings()


def client():
    return get_standard_client(settings())


def count_encrypted(coll, field: str) -> int:
    return coll.count_documents({field: {"$type": "binData"}})


def count_plaintext(coll, field: str) -> int:
    return coll.count_documents({field: {"$type": "string"}})


def truncate_value(value, limit: int = 48):
    if isinstance(value, Binary):
        shown = bytes(value)[:limit].hex()
        return f"BinData(0, {shown}…)  [{len(bytes(value))} bytes]"
    return value


def collection_state(db_name: str, coll_name: str, field: str) -> dict:
    try:
        coll = client()[db_name][coll_name]
        return {
            "ok": True,
            "total": coll.estimated_document_count(),
            "encrypted": count_encrypted(coll, field),
            "plaintext": count_plaintext(coll, field),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


# --- sidebar -------------------------------------------------------------
st.sidebar.markdown("## 🔐 Encryption demos")

try:
    s = settings()
    c = client()
    c.admin.command("ping")
    host = s.mongodb_uri.split("@")[-1].split("/")[0].split("?")[0]
    st.sidebar.success(f"Atlas connected · `{host}`")
    connected = True
except Exception as e:  # noqa: BLE001
    st.sidebar.error("Not connected to Atlas.")
    st.sidebar.caption("Run the scripts' setup first: copy `.env.example` to "
                       "`.env`, set `MONGODB_URI`, and ensure the Automatic "
                       "Encryption Shared Library is available.")
    st.sidebar.caption(f"Details: {e}")
    connected = False

st.sidebar.caption("🧪 Demo data comes from the MongoDB sample datasets "
                   "loaded on the cluster. Key material lives in your local "
                   "`.keys/` file and is never displayed here.")

# --- header --------------------------------------------------------------
st.markdown("# 🔐 CSFLE vs Queryable Encryption")
st.caption("Two client-side field encryption approaches compared on the "
           "existing Atlas cluster. Both keep data encrypted at rest, in "
           "use, and over the wire — the difference is *how* queries work "
           "and what setup each requires.")

if not connected:
    st.error("**No Atlas connection.** Configure `.env` (see sidebar) and reload.")
    st.stop()

csfle_state = collection_state(CSFLE_DB_NAME, CSFLE_COLLECTION_NAME, CSFLE_TARGET_FIELD)
qe_state = collection_state(QE_DB_NAME, QE_COLLECTION_NAME, QE_TARGET_FIELD)

# --- concept comparison ---------------------------------------------------
st.markdown("### How the two approaches compare")

st.markdown("""
| | CSFLE (this demo: deterministic) | Queryable Encryption |
|---|---|---|
| **Encryption algorithm** | `AEAD_AES_256_CBC_HMAC_SHA_512` — deterministic in this demo | `AEAD_AES_256_CBC_HMAC_SHA_512-Encrypted` — always randomized |
| **Supported queries** | Equality only (deterministic). Randomized CSFLE supports no queries. | Equality, and **range** queries on supported types (this demo uses `range` on `limit`) |
| **Ciphertext leakage** | Deterministic leaks equality patterns — repeated values look repeated | No plaintext patterns; queryable via encrypted metadata |
| **Collection setup** | Fields can be encrypted in an existing collection | Must be configured **at collection creation** (plus hidden `enxcol.*` metadata collections) |
| **Key management** | Same: DEKs in a key vault collection, wrapped by a customer master key (local KMS here; Atlas KMS/other providers in production) | Same |
| **Driver requirement** | PyMongo ≥ 4.x with the Automatic Encryption Shared Library | Same, plus MongoDB 7.0+ for range queries |
""")

st.info("**What an authorized application sees vs. everyone else.** A client "
        "with the key material and encryption configuration reads and queries "
        "plaintext normally. Any other client — including Atlas itself — sees "
        "only `BinData` ciphertext. The demos below show both views of the "
        "same document.")

# --- CSFLE demo -----------------------------------------------------------
st.markdown("### Demo 1 — CSFLE on `sample_mflix.users.email`")
st.caption("Deterministic encryption applied in place over the sample users "
           "collection. Equality queries still work; range/other queries do not.")

if not csfle_state["ok"]:
    st.error(f"Cannot read `{CSFLE_DB_NAME}.{CSFLE_COLLECTION_NAME}`: {csfle_state['error']}")
else:
    c1, c2, c3 = st.columns(3)
    c1.metric("Documents", csfle_state["total"])
    c2.metric("Encrypted email", csfle_state["encrypted"])
    c3.metric("Plaintext email", csfle_state["plaintext"])
    if csfle_state["encrypted"] == 0:
        st.warning("Not encrypted yet — run the apply step below (or "
                   "`python3 scripts/csfle_demo.py apply`).")

    with st.expander("Run CSFLE actions", expanded=False):
        st.markdown("**Apply** — encrypts all plaintext `email` values in place "
                    "(a plaintext backup collection `users_csfle_backup` is kept).")
        confirm_apply = st.checkbox("I understand this modifies the shared sample collection", key="csfle_apply")
        if st.button("Apply CSFLE encryption", disabled=not confirm_apply, key="csfle_apply_btn"):
            import csfle_demo
            csfle_demo.apply_encryption()
            st.success("Applied. Rerun happens on next page load — metrics above refresh on reload.")
            st.rerun()

        st.markdown("**Query** — find one document by plaintext email through an "
                    "encrypted client, then show how the same document is stored raw.")
        if st.button("Query one document (encrypted client vs raw view)", key="csfle_query_btn"):
            import csfle_demo
            csfle_demo.query_encrypted(None)
            st.info("Output was printed to the Streamlit server console. "
                    "The raw stored value is ciphertext (`BinData`); the encrypted "
                    "client still matched on plaintext.")

        st.markdown("**Remove** — decrypt everything back to plaintext and drop the backup.")
        confirm_remove = st.checkbox("Confirm decrypt-in-place and backup removal", key="csfle_remove")
        if st.button("Remove CSFLE encryption", disabled=not confirm_remove, key="csfle_remove_btn"):
            import csfle_demo
            csfle_demo.remove_encryption()
            st.rerun()

    st.markdown("**What is stored vs. what is read** (one sample document):")
    coll = client()[CSFLE_DB_NAME][CSFLE_COLLECTION_NAME]
    raw_doc = coll.find_one({CSFLE_TARGET_FIELD: {"$exists": True}})
    if raw_doc:
        st.code(f"Raw stored document (Atlas view, no keys):\n"
                f"  _id   : {raw_doc['_id']}\n"
                f"  name  : {raw_doc.get('name')}\n"
                f"  email : {truncate_value(raw_doc.get(CSFLE_TARGET_FIELD))}",
                language="text")
    st.caption("With the encryption keys, an application reads the same field as "
               "a normal plaintext email. Without them, the value is opaque.")

# --- QE demo ---------------------------------------------------------------
st.markdown("### Demo 2 — Queryable Encryption on `sample_analytics.accounts.limit`")
st.caption("The collection is recreated with an encrypted-field descriptor, so "
           "`limit` supports **range** queries even though stored ciphertext is "
           "randomized.")

if not qe_state["ok"]:
    st.error(f"Cannot read `{QE_DB_NAME}.{QE_COLLECTION_NAME}`: {qe_state['error']}")
else:
    q1, q2 = st.columns(2)
    q1.metric("Documents", qe_state["total"])
    q2.metric("Encrypted `limit`", qe_state["encrypted"])
    has_meta = any(n.startswith("enxcol.") for n in client()[QE_DB_NAME].list_collection_names())
    if has_meta:
        st.success("QE metadata collections (`enxcol.*`) present — this "
                   "collection was created with Queryable Encryption.")
    else:
        st.warning("No `enxcol.*` metadata collections — run the apply step "
                   "below (or `python3 scripts/qe_demo.py apply`).")

    with st.expander("Run QE actions", expanded=False):
        st.markdown("**Apply** — backs up, drops, and recreates "
                    "`sample_analytics.accounts` as an encrypted collection, "
                    "then reinserts the documents.")
        confirm_qe = st.checkbox("I understand this drops and recreates the shared sample collection", key="qe_apply")
        if st.button("Apply Queryable Encryption", disabled=not confirm_qe, key="qe_apply_btn"):
            import qe_demo
            qe_demo.apply_encryption()
            st.rerun()

        st.markdown("**Range query** — `limit` between bounds, through the "
                    "encrypted client, with the raw stored document alongside.")
        qc1, qc2 = st.columns(2)
        lo = qc1.number_input("Min (exclusive)", 0, 20000, 5000, key="qe_min")
        hi = qc2.number_input("Max (exclusive)", 0, 20000, 10000, key="qe_max")
        if st.button("Run range query", key="qe_query_btn"):
            import qe_demo
            qe_demo.range_query(int(lo), int(hi))
            st.info("Output printed to the server console: matching documents "
                    "decrypt normally for the authorized client, while the raw "
                    "ciphertext is randomized (equal plaintext → different ciphertext).")

        st.markdown("**Remove** — restores plaintext documents and drops the backup.")
        confirm_qe_rm = st.checkbox("Confirm restore and backup removal", key="qe_remove")
        if st.button("Remove QE collection", disabled=not confirm_qe_rm, key="qe_remove_btn"):
            import qe_demo
            qe_demo.remove_encryption()
            st.rerun()

    qcoll = client()[QE_DB_NAME][QE_COLLECTION_NAME]
    raw_q = qcoll.find_one({QE_TARGET_FIELD: {"$type": "binData"}})
    if raw_q:
        st.code(f"Raw stored document (Atlas view, no keys):\n"
                f"  account_id : {raw_q.get('account_id')}\n"
                f"  limit      : {truncate_value(raw_q.get(QE_TARGET_FIELD))}\n"
                f"  __safeContent__ : present (QE integrity metadata)",
                language="text")

# --- operational notes -----------------------------------------------------
with st.expander("⚠️ Prerequisites, limitations, and troubleshooting"):
    st.markdown("""
- **Automatic Encryption Shared Library** must be installed and locatable by
  PyMongo. If encryption actions fail, set `CRYPT_SHARED_LIB_PATH` in `.env`.
- **QE range queries** require MongoDB 7.0+ on the server and a driver that
  supports them (PyMongo ≥ 4.4 with the shared library). The cluster here runs
  the version provisioned by `atlas-cluster-provisioning`.
- **Key material**: this demo uses a local master key file (`.keys/`), which is
  fine for a demo only. Production uses a remote KMS (AWS/GCP/Azure/KMIP) —
  never a file on the app host.
- **Never display or export keys.** This GUI intentionally shows ciphertext
  and decrypted *field values* only.
- **Shared sample collections are modified** by the apply/remove actions, so
  both are gated behind confirmation checkboxes. The scripts keep backup
  collections and restore plaintext on remove.
- Troubleshooting: if queries time out or the library isn't found, check the
  CLI scripts first — `python3 scripts/csfle_demo.py decrypt` — they print the
  underlying errors directly.
""")
