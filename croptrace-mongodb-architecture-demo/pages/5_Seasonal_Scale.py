"""Route ⑤: Seasonal scale & operational conversation."""

import pandas as pd
import streamlit as st

from lib.ui import (connection_guard, page_header, presenter_notes, story_arc,
                    synthetic_note)

st.set_page_config(page_title="CropTrace · Seasonal scale & operations",
                   page_icon="⑤", layout="wide")
connection_guard()

page_header("⑤", "Seasonal scale & operational conversation",
            "A talking point about seasonal demand and how to size and operate "
            "Atlas vs Aurora — not a live billing dashboard.")
story_arc(
    problem="Residue-risk workloads spike around planting and harvest and are "
            "quiet in between.",
    interaction="Adjust the workload assumptions, read the seasonal shape, and "
                "walk the sizing/cost checklist together.",
    mechanism="Atlas Compute Auto-Scale responds to sustained load; the shape "
              "of the workload drives the operational plan.",
    tradeoff="Aurora offers its own scaling models; the right answer depends on "
             "the validated numbers, not on slogans.")

presenter_notes(
    talk_track="CropTrace traffic is seasonal — busy at planting and harvest, "
               "quiet otherwise. This page is a conversation starter, not a "
               "bill. I set the workload assumptions, we look at the demand "
               "shape, and then we walk a checklist to size and operate on both "
               "Atlas and Aurora. I won't quote dollars unless we plug in real "
               "pricing inputs; instead we agree on the questions that make a "
               "credible comparison.",
    click_path=["Point out the 'Synthetic demo scenario' label",
                "Edit baseline/peak and data size",
                "Read the seasonal curve", "Walk the Atlas vs Aurora checklist",
                "Note autoscaling vs serverless distinction"],
    takeaway="Size and operate from validated workload numbers; autoscaling is "
             "not the same as a function-style serverless model.",
    caveat="No cost or product-packaging claims without verified pricing "
           "inputs — Aurora may be the better operational fit for some teams.")

st.warning("🧪 **Synthetic demo scenario** — the demand curve below is "
           "illustrative, not measured from any real CropTrace deployment.")

st.markdown("#### ⚙️ Workload assumptions (editable)")
c1, c2, c3 = st.columns(3)
baseline = c1.number_input("Baseline requests/sec", 1, 100_000, 200, step=50)
peak = c2.number_input("Peak requests/sec", 1, 500_000, 2_000, step=100)
data_gb = c3.number_input("Working data size (GB)", 1, 100_000, 120, step=10)
c4, c5, c6 = st.columns(3)
read_pct = c4.slider("Read %", 0, 100, 80)
growth = c5.slider("Annual growth %", 0, 200, 30)
latency_ms = c6.number_input("Latency target (ms, p95)", 1, 5_000, 50, step=5)

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# Two seasonal peaks: planting (spring) and harvest (late summer).
SHAPE = [0.15, 0.2, 0.55, 0.9, 1.0, 0.6, 0.5, 0.85, 1.0, 0.7, 0.3, 0.15]
demand = pd.DataFrame({
    "month": MONTHS,
    "requests/sec": [round(baseline + (peak - baseline) * s) for s in SHAPE],
})
st.markdown(f"**Read/write mix:** {read_pct}% read / {100 - read_pct}% write · "
            f"**growth:** {growth}%/yr · **p95 target:** {latency_ms} ms · "
            f"**data:** {data_gb} GB")
st.area_chart(demand, x="month", y="requests/sec", height=260)

st.markdown("---")
st.markdown("#### ✅ Sizing / cost comparison checklist (Atlas & Aurora)")
CHECKLIST = [
    "Instance/cluster sizing for baseline vs peak requests-per-second",
    "Autoscaling behaviour and the latency of scale-up / scale-down events",
    "Availability requirements (multi-AZ / multi-region) and failover impact",
    "Throughput and IOPS at peak, and how they are provisioned or billed",
    "Workload shape: sustained vs spiky, and read/write split",
    "Storage growth over the season and year-over-year",
    "Total operational effort: patching, backups, monitoring, scaling",
    "Documented pricing inputs before any dollar estimate is produced",
]
cols = st.columns(2)
for i, item in enumerate(CHECKLIST):
    cols[i % 2].checkbox(item, key=f"chk_{i}")

st.info("💡 **Autoscaling ≠ serverless.** Atlas Compute Auto-Scale resizes a "
        "running cluster in response to sustained load; it is not a "
        "function-style, scale-to-zero serverless model. Do not assert current "
        "product packaging or pricing without verifying it against the "
        "connected environment or official documentation.")
st.caption("No dollar figure is shown here on purpose — this route exposes the "
           "questions for a credible comparison, not an unsupported estimate.")

st.markdown("---")
if st.button("🔄 Reset demo (restore default assumptions)"):
    for k in list(st.session_state.keys()):
        if k.startswith("chk_"):
            del st.session_state[k]
    st.rerun()
synthetic_note()
