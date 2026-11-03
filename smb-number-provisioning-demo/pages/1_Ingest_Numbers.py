"""① Ingest numbers — portal entry, CSV batch upload, direct-API simulation.

All three routes call the same `process_ingest` service, so validation and
cap enforcement cannot diverge. Every write requires an explicit button.
"""

import csv
import io
import json
import uuid

import streamlit as st

from lib.cap_service import (DEFAULT_CAP, BatchResult, process_ingest,
                             reactivate_number, transfer_number)
from lib.config import RACE_ACCOUNT_ID
from lib.sample_data import FICTIONAL_TNS, seed_demo
from lib.ui import (connection_guard, demo_scope_note, err_badge, ok_badge,
                    synthetic_note)

st.set_page_config(page_title="Ingest numbers · SMB provisioning demo",
                   page_icon="⬇️", layout="wide")
connection_guard()

st.markdown("# ① Ingest numbers")
st.caption("Three entry routes, one shared validation and ingestion service. "
           "The account supplies its own numbers; the demo marks vetting as a "
           "conceptual step and never performs real verification.")
synthetic_note()
demo_scope_note()


def run_ingest(account_id: str, items: list[dict], channel: str,
               idem_key: str) -> BatchResult:
    from lib.ui import db as cached_db
    return process_ingest(cached_db(), account_id, items, channel,
                          cap=DEFAULT_CAP, idempotency_key=idem_key)


def render_result(res: BatchResult) -> None:
    if res.replayed:
        st.info("🔁 Idempotent replay: this idempotency key was seen before, "
                "so the original per-item outcomes are shown again — no new "
                "assets, no double-counted capacity.")
    for r in res.results:
        if r.ok:
            st.markdown(f"{ok_badge(r.code)} · `{r.tn}` ({r.number_type}) "
                        f"— {r.detail}")
        else:
            st.markdown(f"{err_badge(r.code)} · `{r.tn or '—'}` "
                        f"({r.number_type or '—'}) — {r.detail}")
    st.caption(f"channel=`{res.channel}` · idempotencyKey=`{res.idempotency_key}`"
               f" · write path: "
               f"{'transactions' if res.used_transactions else 'reservation + compensation (non-atomic fallback)'}")


with st.expander("Step 0 · Seed synthetic demo data (idempotent)",
                 expanded=False):
    st.caption("Creates the synthetic accounts, a few assets, and counters "
               "with upserts only. Never drops or overwrites anything.")
    if st.button("Seed demo data", key="seed"):
        from lib.ui import db as cached_db
        st.session_state["seed_info"] = seed_demo(cached_db())
    if st.session_state.get("seed_info"):
        st.success(f"Seeded (idempotent): {st.session_state['seed_info']}")

tab_portal, tab_batch, tab_api, tab_re = st.tabs(
    ["🖥️ Portal entry", "📄 Batch CSV upload", "🔌 Direct API (JSON)",
     "♻️ Reactivation & transfer"])

with tab_portal:
    st.markdown("**Portal-style single entry.** The same service path as the "
                "other routes — only the channel differs.")
    account = st.text_input("accountId", "ACC-SMB-0001", key="p_account")
    tn = st.text_input("Telephone number (fictional range +1-555-01xx)",
                       FICTIONAL_TNS[5], key="p_tn")
    num_type = st.selectbox("Number type", ["local", "toll_free"], key="p_type")
    if st.button("Submit via portal", key="p_submit"):
        res = run_ingest(account.strip(),
                         [{"tn": tn.strip(), "type": num_type}],
                         "portal", f"portal-{uuid.uuid4().hex}")
        st.session_state["portal_result"] = res
    if st.session_state.get("portal_result"):
        render_result(st.session_state["portal_result"])

with tab_batch:
    st.markdown("**Batch-file upload.** Rows are processed **in file order**; "
                "every row is reported as accepted or rejected — malformed "
                "rows are never silently skipped. Rows after the cap is "
                "reached are rejected.")
    sample = "tn,type\n" + "\n".join(
        f"{t},local" for t in FICTIONAL_TNS[20:26])
    st.download_button("Download sample CSV", sample.encode(),
                       "sample_numbers.csv", "text/csv")
    b_account = st.text_input("accountId", "ACC-SMB-0002", key="b_account")
    up = st.file_uploader("CSV with header `tn,type`", type="csv")
    if up is not None and st.button("Upload batch", key="b_submit"):
        reader = csv.DictReader(io.StringIO(up.getvalue().decode()))
        items, bad = [], []
        for lineno, row in enumerate(reader, start=2):
            tn_v = (row.get("tn") or "").strip()
            ty_v = (row.get("type") or "local").strip() or "local"
            if tn_v:
                items.append({"tn": tn_v, "type": ty_v})
            else:
                bad.append(lineno)
        st.caption(f"Parsed {len(items)} rows in file order"
                   + (f"; {len(bad)} malformed row(s) reported below"
                      if bad else ""))
        res = run_ingest(b_account.strip(), items, "batch",
                         f"batch-{uuid.uuid4().hex}")
        for lineno in bad:
            st.markdown(f"{err_badge('422 MALFORMED_ROW')} · row {lineno} — "
                        f"missing `tn`; not silently skipped")
        st.session_state["batch_result"] = (res, len(bad))
    if st.session_state.get("batch_result"):
        res, bad = st.session_state["batch_result"]
        render_result(res)
        if res.rejected:
            st.warning(f"{len(res.rejected)} row(s) rejected — including any "
                       f"rows after the cap was reached. No numbers were "
                       f"saved for rejected rows.")

with tab_api:
    st.markdown("**Direct-API simulation.** A JSON array of items; the "
                "response reports one result per submitted item, exactly as "
                "a bulk API would.")
    api_account = st.text_input("accountId ", "ACC-SMB-0002", key="a_account")
    default_payload = json.dumps(
        [{"tn": FICTIONAL_TNS[30], "type": "local"},
         {"tn": FICTIONAL_TNS[20], "type": "local"}], indent=2)
    payload = st.text_area("JSON items", default_payload, height=160,
                           key="a_payload")
    if st.button("POST simulated bulk request", key="a_submit"):
        try:
            parsed = json.loads(payload)
            assert isinstance(parsed, list)
        except Exception:
            st.error("Payload must be a JSON array of {\"tn\", \"type\"} "
                     "objects. Each item gets a visible result.")
            parsed = None
        if parsed is not None:
            res = run_ingest(api_account.strip(), parsed, "direct_api",
                             f"api-{uuid.uuid4().hex}")
            st.session_state["api_result"] = res
    if st.session_state.get("api_result"):
        render_result(st.session_state["api_result"])

with tab_re:
    st.markdown("**Reactivation and transfer both count as additions** for "
                "cap enforcement — they reserve capacity on the destination "
                "account through the same atomic guard.")
    re_col1, re_col2 = st.columns(2)
    with re_col1:
        st.markdown("**Reactivate** the released number on `ACC-SMB-0002`")
        if st.button("Reactivate +15550110", key="re_btn"):
            from lib.ui import db as cached_db
            ok, msg = reactivate_number(cached_db(), "ACC-SMB-0002",
                                        "+15550110", "local")
            (st.success if ok else st.error)(f"{msg}")
            st.caption("Counts as an addition: capacity is reserved first "
                       "and the state moves to `active`.")
    with re_col2:
        st.markdown("**Transfer** a number from `ACC-SMB-0001` to "
                    "`ACC-SMB-0002`")
        if st.button("Transfer +15550100", key="tf_btn"):
            from lib.ui import db as cached_db
            ok, msg = transfer_number(cached_db(), "ACC-SMB-0001",
                                      "ACC-SMB-0002", "+15550100", "local")
            (st.success if ok else st.error)(f"{msg}")
            st.caption("Simplification: the transfer is shown as "
                       "release-and-reserve on the destination; the source "
                       "counter is not decremented because capacity moved "
                       "with the number in this single-tenant model.")
