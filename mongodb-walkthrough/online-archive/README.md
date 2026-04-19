# Online Archive — Hot/Cold Data Tiering

This demo configures an Atlas Online Archive rule on `sample_mflix.movies`, then runs timed queries to show the difference in response time between live (hot) and archived (cold) data.

---

## What is Online Archive?

Atlas Online Archive automatically moves infrequently accessed documents from your cluster (hot tier, SSD-backed) to Atlas-managed cloud object storage (cold tier). A **Data Federation** endpoint is created that queries both tiers transparently — applications use a single connection string and see the full dataset regardless of which tier a document lives on.

```
                   ┌─────────────────────────────────────┐
Application ──────►│  Atlas Data Federation endpoint     │
                   │  (single connection string)         │
                   └────────────┬──────────────┬─────────┘
                                │              │
                   ┌────────────▼──┐  ┌────────▼──────────┐
                   │  Live cluster │  │  Cloud object      │
                   │  (hot tier)   │  │  storage (cold)    │
                   │  ~ms latency  │  │  ~2–4 s latency    │
                   └───────────────┘  └────────────────────┘
```

The archive rule in this demo targets the `released` date field in `sample_mflix.movies`. Movies released more than `ARCHIVE_EXPIRE_AFTER_DAYS` days ago are eligible to be archived.

---

## Files

| File | Purpose |
|---|---|
| `setup_archive.py` | Creates the archive rule via the Atlas Admin API. Run once. |
| `query_demo.py` | Runs timed queries against the live cluster and the federated endpoint. |
| `.env.example` | Environment variable template. |
| `requirements.txt` | Python dependencies. |

---

## Setup

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`. The minimum required for `setup_archive.py`:

```env
ATLAS_PUBLIC_KEY=...
ATLAS_PRIVATE_KEY=...
ATLAS_PROJECT_ID=...
CLUSTER_NAME=...
MONGODB_URI=...
```

`FEDERATED_URI` is only needed for the second script and can be added later.

---

## Step 1 — Configure the archive rule

```bash
python3 setup_archive.py
```

This calls the Atlas Admin API to create a DATE-based archive rule. The script is idempotent — re-running it reports the existing rule rather than creating a duplicate.

Atlas archives data on a **daily schedule**. After the rule is created, wait for the first archive run before proceeding (visible in Atlas UI → Data Federation).

---

## Step 2 — Add the federated connection string

Once archiving has run, Atlas creates a Data Federation endpoint automatically.

1. Atlas UI → **Data Federation** → select the federated instance
2. Click **Connect** and copy the connection string
3. Add it to `.env` as `FEDERATED_URI`

---

## Step 3 — Run the query demo

```bash
python3 query_demo.py
```

The script runs three queries against the **live cluster** (hot tier only) and the same three queries against the **federated endpoint** (hot + cold):

| Query | Expected behaviour |
|---|---|
| Recent documents (after cutoff year) | Fast on both endpoints — data is on the live cluster |
| Older documents (before cutoff year) | Fast on live cluster (but returns 0 if archived); 2–4 s on federated endpoint |
| Full scan | Federated endpoint is slower — it combines both tiers |

---

## Key talking points

- The application does not need to know which tier a document lives on — the federated endpoint handles routing
- Archived data is still fully queryable; the latency trade-off (2–4 s) is acceptable for infrequently accessed historical records
- Storage cost for the cold tier is significantly lower than keeping all data on a live cluster
- The archive rule can be paused, modified, or deleted at any time; archived data can be restored
