"""Streamlit GUI for the Online Archive demo.

    streamlit run app.py

Shows hot (live cluster) vs cold (Online Archive / Data Federation) data
side by side with timed queries. Requires the archive rule and federated
endpoint to be configured by setup_archive.py first; until then the GUI
shows a clear "not configured" state and never pretends archiving exists.
"""

from __future__ import annotations

import os
import time

import streamlit as st
from dotenv import load_dotenv
from pymongo import MongoClient

st.set_page_config(page_title="Atlas Online Archive", page_icon="🗄️", layout="wide")

load_dotenv()

MONGODB_URI = os.environ.get("MONGODB_URI", "")
FEDERATED_URI = os.environ.get("FEDERATED_URI", "")
DB_NAME = os.environ.get("DB_NAME", "sample_mflix")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "movies")
CUTOFF_YEAR = int(os.environ.get("ARCHIVE_CUTOFF_YEAR", "2001"))


@st.cache_resource
def live_client():
    return MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)


@st.cache_resource
def federated_client():
    if not FEDERATED_URI:
        return None
    return MongoClient(FEDERATED_URI, serverSelectionTimeoutMS=60_000)


def timed_count(coll, query) -> tuple[int, float]:
    start = time.time()
    count = coll.count_documents(query)
    return count, (time.time() - start) * 1000


# --- sidebar ---------------------------------------------------------------
st.sidebar.markdown("## 🗄️ Online Archive")
live_ok = False
fed_ok = False

if MONGODB_URI:
    try:
        live_client().admin.command("ping")
        host = MONGODB_URI.split("@")[-1].split("/")[0].split("?")[0]
        st.sidebar.success(f"Live cluster connected · `{host}`")
        live_ok = True
    except Exception as e:  # noqa: BLE001
        st.sidebar.error(f"Live cluster not reachable: {e}")
else:
    st.sidebar.error("Set `MONGODB_URI` in `.env`.")

if FEDERATED_URI:
    try:
        federated_client().admin.command("ping")
        st.sidebar.success("Data Federation endpoint connected")
        fed_ok = True
    except Exception as e:  # noqa: BLE001
        st.sidebar.warning(f"Federated endpoint not reachable: {e}")
else:
    st.sidebar.info("`FEDERATED_URI` not set — Online Archive not configured "
                    "for this environment yet.")

st.sidebar.caption("🧪 Data is the MongoDB sample movie dataset — synthetic demo "
                   "use only. Credentials stay in `.env` and are never displayed.")

# --- header ----------------------------------------------------------------
st.markdown("# 🗄️ Atlas Online Archive — Hot/Cold Data Tiering")
st.caption("Atlas Online Archive moves infrequently accessed documents from the "
           "live cluster (hot tier) to Atlas-managed cloud object storage (cold "
           "tier). A Data Federation endpoint queries both tiers through one "
           "connection string, so applications never need to know where a "
           "document lives.")

st.markdown(f"""
| Tier | Storage | Filter (this demo) | Latency profile |
|---|---|---|---|
| **Hot (live)** | Cluster SSD | `year >= {CUTOFF_YEAR}` | Milliseconds |
| **Cold (archived)** | Cloud object storage | `year < {CUTOFF_YEAR}` | Seconds (reads via Data Federation) |
""")

if not live_ok:
    st.error("**No live connection.** Copy `.env.example` to `.env`, set "
             "`MONGODB_URI` to the cluster from `atlas-cluster-provisioning`, "
             "and reload.")
    st.stop()

live_coll = live_client()[DB_NAME][COLLECTION_NAME]

# --- archive configuration state -------------------------------------------
archive_configured = fed_ok and FEDERATED_URI

if not archive_configured:
    st.warning(
        "**Online Archive is not configured for this environment.** An archive "
        "rule must be created by an operator through the Atlas Admin API or UI; "
        "this app never creates or alters one on its own. To enable the live "
        "demonstration:"
    )
    st.code("python3 setup_archive.py", language="bash")
    st.markdown(
        f"Then wait for the **first daily archive run** (Atlas UI → Online "
        f"Archive), add the `FEDERATED_URI` from **Atlas UI → Online Archive → "
        f"Connect → Connect to Cluster and Online Archive** to `.env`, and "
        f"reload this page. Until then, only the live (hot) tier below is real; "
        f"no archived-data results are shown, simulated or otherwise."
    )
else:
    st.success("Archive configured — queries below run against both the live "
               "cluster and the federated (hot + cold) endpoint.")

# --- live tier state ---------------------------------------------------------
st.markdown("### Live (hot) tier")

try:
    total_live, _ = timed_count(live_coll, {})
    hot_count, ms_hot = timed_count(live_coll, {"year": {"$gte": CUTOFF_YEAR}})
    cold_on_live, ms_cold = timed_count(live_coll, {"year": {"$lt": CUTOFF_YEAR}})
    m1, m2, m3 = st.columns(3)
    m1.metric("Documents on live cluster", f"{total_live:,}")
    m2.metric(f"`year >= {CUTOFF_YEAR}` (hot)", f"{hot_count:,}", f"{ms_hot:.0f} ms")
    m3.metric(f"`year < {CUTOFF_YEAR}` (archivable)", f"{cold_on_live:,}", f"{ms_cold:.0f} ms")

    if archive_configured and cold_on_live > 0:
        st.info("Documents older than the cutoff are still on the live cluster — "
                "Atlas archives on a **daily schedule**, so the first run may not "
                "have happened yet. Check Atlas UI → Online Archive → *Last "
                "Archive Run*.")

    st.markdown("### Live vs. federated query timing")
    if not archive_configured:
        st.markdown("Federated timing unavailable — see configuration state above.")
    else:
        fed_coll = federated_client()[DB_NAME][COLLECTION_NAME]
        queries = {
            f"Hot range: year >= {CUTOFF_YEAR}": {"year": {"$gte": CUTOFF_YEAR}},
            f"Cold range: year < {CUTOFF_YEAR}": {"year": {"$lt": CUTOFF_YEAR}},
            "Full collection (count all)": {},
        }
        rows = []
        for label, query in queries.items():
            live_count, live_ms = timed_count(live_coll, query)
            fed_count, fed_ms = timed_count(fed_coll, query)
            rows.append({
                "Query": label,
                "Live results": f"{live_count:,}",
                "Live time": f"{live_ms:.0f} ms",
                "Federated results": f"{fed_count:,}",
                "Federated time": f"{fed_ms:.0f} ms",
            })
        st.dataframe(rows, use_container_width=True)
        st.caption("The federated endpoint returns the union of both tiers. Cold "
                   "results are slower because they are read from cloud object "
                   "storage via Data Federation — the trade-off for much cheaper "
                   "long-term retention. Numbers vary by run and region; this demo "
                   "shows relative behavior, not benchmarks.")

        st.markdown("### Where does a specific title live?")
        title = st.text_input("Movie title (exact match)")
        if title:
            live_match = live_coll.find_one({"title": title}, {"title": 1, "year": 1})
            fed_match = federated_client()[DB_NAME][COLLECTION_NAME].find_one(
                {"title": title}, {"title": 1, "year": 1})
            if fed_match and not live_match:
                st.error(f"❄️ **Cold (archived)** — `{title}` ({fed_match.get('year')}) "
                         f"is only visible through the federated endpoint.")
            elif live_match:
                st.success(f"🔥 **Hot (live)** — `{title}` ({live_match.get('year')}) "
                           f"is on the live cluster.")
            else:
                st.info(f"`{title}` not found on either endpoint.")

except Exception as e:  # noqa: BLE001
    st.error(f"Query failed: {e}")
    st.caption("If the sample dataset is missing, load it: Atlas UI → your "
               "cluster → ⋯ → Load Sample Dataset.")

# --- talking points ----------------------------------------------------------
with st.expander("🎤 Key talking points"):
    st.markdown("""
- Applications use **one connection string**; the federated endpoint routes to
  whichever tier holds the data.
- Archived data stays **fully queryable** — the trade-off is seconds of latency,
  not inaccessibility.
- Cold storage is significantly cheaper than keeping everything on the cluster,
  which is the point of retention policies for aging data.
- **Partition fields** in the archive rule act as the cold tier's index; the
  live tier still uses a standard index on `year` (created by `setup_archive.py`).
- The rule can be paused, changed, or deleted; `teardown_archive.py` can
  rehydrate archived documents before deleting the rule.

**Prerequisites** (operator actions — this app never performs them):
1. `python3 setup_archive.py` — creates the index and archive rule via the
   Atlas Admin API (needs `ATLAS_PUBLIC_KEY`/`ATLAS_PRIVATE_KEY`/`ATLAS_PROJECT_ID`).
2. Wait for the first daily archive run.
3. Add `FEDERATED_URI` to `.env`.
""")
