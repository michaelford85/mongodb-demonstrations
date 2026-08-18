"""Route ④: ACID transaction scenario."""

import pandas as pd
import streamlit as st

from lib.atlas_client import PLOT_IDS, db_name, get_client
from lib.sample_data import build_plots_and_events, build_products
from lib.transactions import (audit_count, change_plan, list_audit_events)
from lib.ui import (connection_guard, db, page_header, presenter_notes,
                    seed_guard, story_arc, synthetic_note)

st.set_page_config(page_title="CropTrace · ACID transactions",
                   page_icon="④", layout="wide")
connection_guard()
seed_guard()
database = db()

page_header("④", "ACID transaction scenario",
            "A grower changes a treatment plan and a linked audit record is "
            "written — both, or neither.")
story_arc(
    problem="Changing a plan and recording the audit event must not drift "
            "apart: a partial write would leave an untracked change.",
    interaction="Run the change with a deliberate mid-transaction failure, then "
                "run it successfully and see the audit trail.",
    mechanism="A session-scoped multi-document transaction; abort rolls both "
              "writes back atomically.",
    tradeoff="Transactions are fully supported, but a good document model keeps "
             "most operations single-document — reach for them when two "
             "independent documents must change together.")

presenter_notes(
    talk_track="Here two different documents must change together: the "
               "treatment plan and a separate audit event. I wrap both in one "
               "transaction. First I inject a failure right after the treatment "
               "update — the transaction aborts, and you'll see the treatment "
               "is unchanged and no audit row exists. Then I run it for real: "
               "both persist, and the audit trail shows the change. The honest "
               "point: transactions are here when you need them, but you should "
               "model so that most operations touch a single document.",
    click_path=["Pick a treatment", "Set the new status/dose",
                "Run WITH simulated failure → nothing persisted",
                "Run SUCCESSFULLY → both persisted",
                "Review the audit trail"],
    takeaway="Multi-document transactions give all-or-nothing consistency when "
             "the model genuinely needs it.",
    caveat="If nearly every operation needs multi-document transactions, that "
           "may signal an over-normalized model — or a relational fit.")

plot_id = st.selectbox("Plot", PLOT_IDS)
treatments = list(database.treatment_events.find(
    {"plot_id": plot_id}, {"_id": 0, "treatment_id": 1, "status": 1,
     "dose_l_per_ha": 1}).sort("treatment_id", 1))
if not treatments:
    st.info("No treatments for this plot — pick another.")
    st.stop()
tlabels = {f"{t['treatment_id']} · {t['status']} · {t['dose_l_per_ha']} L/ha":
           t["treatment_id"] for t in treatments}
tid = tlabels[st.selectbox("Treatment", list(tlabels.keys()))]

c1, c2 = st.columns(2)
new_status = c1.selectbox("New status", ["planned", "applied", "cancelled"])
new_dose = c2.number_input("New dose (L/ha)", min_value=0.0, value=1.0, step=0.1)

st.markdown("#### Run the transaction")
col_fail, col_ok = st.columns(2)


def _show_result(res: dict) -> None:
    before, after = res["treatment_before"], res["treatment_after"]
    st.write(f"**Committed:** {res['committed']} · "
             f"**Audit persisted:** {res['audit_persisted']}")
    st.dataframe(pd.DataFrame([
        {"field": "status", "before": before.get("status"),
         "after": after.get("status")},
        {"field": "dose_l_per_ha", "before": before.get("dose_l_per_ha"),
         "after": after.get("dose_l_per_ha")},
    ]), use_container_width=True, hide_index=True)


with col_fail:
    if st.button("💥 Run WITH simulated failure", use_container_width=True):
        res = change_plan(get_client(), db_name(), treatment_id=tid,
                          new_status=new_status, new_dose=float(new_dose),
                          fail=True)
        st.error("Transaction aborted after the first write — neither change "
                 "persisted.")
        _show_result(res)
with col_ok:
    if st.button("✅ Run SUCCESSFULLY", type="primary",
                 use_container_width=True):
        res = change_plan(get_client(), db_name(), treatment_id=tid,
                          new_status=new_status, new_dose=float(new_dose),
                          fail=False)
        st.success("Both writes committed atomically.")
        _show_result(res)

st.markdown("---")
st.markdown(f"#### 🧾 Audit trail for `{plot_id}` "
            f"(total audit docs: {audit_count(database)})")
events = list_audit_events(database, plot_id)
if events:
    st.dataframe(pd.DataFrame(events), use_container_width=True, hide_index=True)
else:
    st.caption("No audit events for this plot yet.")

st.markdown("---")
if st.button("🔄 Reset demo (restore treatments, clear audit trail)"):
    products = build_products()
    _, events, _ = build_plots_and_events(products)
    for ev in events:
        database.treatment_events.replace_one(
            {"treatment_id": ev["treatment_id"]}, ev, upsert=True)
    database.audit_events.delete_many({})
    st.toast("Treatments restored and audit trail cleared.")
    st.rerun()
synthetic_note()
