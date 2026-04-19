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

The archive rule in this demo targets the `year` field in `sample_mflix.movies`. Every document in the collection has this integer field, making the hot/cold split clean and predictable. Movies with `year < ARCHIVE_CUTOFF_YEAR` are moved to cold storage; newer movies stay on the live cluster.

---

## Files

| File | Purpose |
|---|---|
| `setup_archive.py` | Creates the archive rule via the Atlas Admin API. Run once. |
| `query_demo.py` | Runs timed queries against the live cluster and the federated endpoint. |
| `teardown_archive.py` | Deletes an archive rule and its federated instance. |
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

# Movies with year < this value are archived. 2001 gives a good hot/cold split.
ARCHIVE_CUTOFF_YEAR=2001

# Required for multi-region clusters — Atlas cannot auto-determine the archive
# storage region when a cluster spans more than one region. Use any region the
# cluster already has nodes in (e.g. the primary region).
ARCHIVE_CLOUD_PROVIDER=AWS
ARCHIVE_REGION=US_EAST_1
```

`FEDERATED_URI` is only needed for the second script and can be added later.

---

## Step 1 — Configure the archive rule

```bash
python3 setup_archive.py
```

This calls the Atlas Admin API to create a CUSTOM-based archive rule on the `year` field (`year < ARCHIVE_CUTOFF_YEAR`). The script is idempotent — re-running it reports the existing rule rather than creating a duplicate.

Atlas archives data on a **daily schedule**. After the rule is created, wait for the first archive run before proceeding. Progress is visible in Atlas UI → **Online Archive** (the rule card shows Last Archive Run and Total Data Archived).

---

## Step 2 — Add the federated connection string

Once archiving has run, Atlas creates a federated endpoint automatically.

1. Atlas UI → **Online Archive** → **Connect**
2. Select **"Connect to Cluster and Online Archive"** — this queries both tiers
3. Copy the connection string (it starts with `mongodb://`, not `mongodb+srv://`)
4. Add it to `.env` as `FEDERATED_URI`

---

## Step 3 — Run the query demo

```bash
python3 query_demo.py
```

The script runs three queries against the **live cluster** (hot tier only) and the same three queries against the **federated endpoint** (hot + cold):

| Query | Expected behaviour |
|---|---|
| `year >= CUTOFF_YEAR` | Fast on both endpoints — data is on the live cluster |
| `year < CUTOFF_YEAR` | Returns 0 on live cluster (archived); 2–4 s on federated endpoint |
| Full scan | Federated endpoint is slower — it combines both tiers |

---

## Teardown

```bash
python3 teardown_archive.py
```

If only one archive rule exists on the cluster it will be identified automatically. If multiple exist (e.g. from a previous failed run), the script lists them and exits — set `ARCHIVE_ID` in your `.env` to the target ID and re-run:

```bash
# Override with a different env file entirely
python3 teardown_archive.py path/to/other.env
```

Deleting the archive rule also removes the federated endpoint and all data in cloud object storage.

---

## Key talking points

- The application does not need to know which tier a document lives on — the federated endpoint handles routing
- Archived data is still fully queryable; the latency trade-off (2–4 s) is acceptable for infrequently accessed historical records
- Storage cost for the cold tier is significantly lower than keeping all data on a live cluster
- The archive rule can be paused, modified, or deleted at any time; archived data can be restored
