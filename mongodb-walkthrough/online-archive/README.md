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

The archive rule in this demo targets the `year` field in `sample_mflix.movies`. Movies with `year < ARCHIVE_CUTOFF_YEAR` are moved to cold storage; newer movies stay on the live cluster.

> **Note on data quality:** a small number of documents in the sample dataset store `year` as a garbled string (e.g. `"1981è"`, `"1994è1998"`) rather than an integer. Because BSON orders all strings after all numbers, a purely numeric `$lt` comparison would leave those documents on the hot tier. The archive query uses an `$or` to also catch string-typed `year` values — all of which predate the cutoff in practice.

---

## Indexing and query performance

Indexes matter at both storage tiers, but in different ways.

### Hot tier — standard MongoDB index

`setup_archive.py` creates an index on `year` before configuring the archive rule:

```python
coll.create_index([("year", ASCENDING)], name="year_1")
```

This index serves two purposes:

1. **Archive daemon efficiency** — when Atlas runs its daily archive job it evaluates the CUSTOM criteria query (`year < 2001`) against every document in the collection. Without an index this is a full collection scan on every run. With the index, Atlas can jump directly to the matching range.
2. **Hot-tier query performance** — after archiving, the live cluster holds only recent documents (`year >= 2001`). Queries that filter on `year` (the common case) use the same index rather than scanning the remaining documents.

### Cold tier — partition fields as an index

When documents are moved to cloud object storage they are organised into *partitions* according to the `partitionFields` defined in the archive rule. This demo uses:

```
year  (order 0)  →  title  (order 1)
```

Partition fields function as the index for the cold tier. When the federated endpoint receives a query that filters on `year`, Atlas can skip every partition whose year range does not overlap the filter — it reads only the relevant objects from cloud storage rather than scanning everything. Without well-chosen partition fields every query against cold data would scan the full archive.

For example, suppose you are configuring the online archive for the movies collection in the `sample_mflix` database. If your archived field is the `year` date field, which you moved to the third position, your first queried field is `title`, and your second queried field is `plot`, your partition will look similar to the following:
```
/title/plot/year
```
Atlas creates partitions first for the `title` field, followed by the `plot` field, and then the `year` field. Atlas uses the partitions for queries on the following fields:
- the title field,
- the title field and the plot field,
- the title field and the plot field and the released field.

**Guidance for choosing partition fields:**

| Consideration | Recommendation |
|---|---|
| Field used most often in filters | Put it first (coarsest partition boundary) |
| High-cardinality field | Good for partitioning — creates smaller, targeted partitions |
| Field used in range queries | Works well as a partition key |
| Maximum partition fields | 2–3; beyond that partitions become too granular to help |

---

## Files

| File | Purpose |
|---|---|
| `setup_archive.py` | Creates the index and archive rule via the Atlas Admin API. Run once. |
| `query_demo.py` | Runs timed queries against the live cluster and the federated endpoint. |
| `title_lookup.py` | Looks up a specific movie by title on both endpoints to show which tier it lives on. |
| `teardown_archive.py` | Optionally rehydrates archived data, then deletes the archive rule. |
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

# Online Archive stores data in AWS S3 or Azure Blob Storage only — GCP is not
# supported as a data process region even if the cluster itself runs on GCP.
# Pick an AWS or Azure region geographically close to your cluster nodes.
ARCHIVE_CLOUD_PROVIDER=AWS
ARCHIVE_REGION=US_EAST_1
```

`FEDERATED_URI` is only needed for the query scripts and can be added later.

---

## Step 1 — Configure the index and archive rule

```bash
python3 setup_archive.py
```

The script first creates an index on `year` (see [Indexing and query performance](#indexing-and-query-performance) above), then calls the Atlas Admin API to create a CUSTOM-based archive rule. The script is idempotent — re-running it reports the existing rule rather than creating a duplicate.

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

The script runs three queries twice — once against each connection string:

| Connection string | Env var | Tiers queried |
|---|---|---|
| Regular cluster URI (`mongodb+srv://...`) | `MONGODB_URI` | Hot tier only |
| Federated endpoint URI (`mongodb://...`) | `FEDERATED_URI` | Hot + cold tiers |

> The federated endpoint uses `mongodb://` (not `mongodb+srv://`). Copy it from Atlas UI → **Online Archive** → **Connect** → **"Connect to Cluster and Online Archive"**.

| Query | Hot tier only (`MONGODB_URI`) | Hot + cold (`FEDERATED_URI`) |
|---|---|---|
| `year >= CUTOFF_YEAR` | Fast — data is on the live cluster | Fast — same live data, slight overhead |
| `year < CUTOFF_YEAR` | 0 documents (data has been archived) | 2–4 s — reads from cloud object storage |
| Full scan | Live documents only | All documents, slower — combines both tiers |

---

## Step 4 — Look up a specific title (optional)

```bash
python3 title_lookup.py "The Matrix"      # archived — year 1999
python3 title_lookup.py "Curious George"  # live — year 2006
python3 title_lookup.py                   # prompts for a title
```

The script searches both endpoints and labels each result `hot (live)` or `cold (archived)`, making it easy to show during a demo exactly which tier a named document lives on.

---

## Teardown

```bash
python3 teardown_archive.py
```

The script will ask whether you want to **rehydrate** — restore archived documents back to the live cluster — before deleting the archive rule. If `MONGODB_URI` and `FEDERATED_URI` are both set in `.env`, rehydration is available:

```
Restore archived documents back to the live cluster before deleting? [y/N]:
```

Rehydration reads all documents matching the archive criteria from the federated endpoint and inserts them back into the live cluster in batches. It skips any document that already exists on the live cluster (duplicate key errors are handled gracefully).

> **Important:** deleting the archive rule also removes the associated Data Federation endpoint. Any data remaining in cloud object storage is **permanently deleted** and cannot be recovered. Rehydrate first if you need the data back on the live cluster.

If only one archive rule exists on the cluster it will be identified automatically. If multiple exist (e.g. from a previous failed run), the script lists them and exits — set `ARCHIVE_ID` in your `.env` to the target ID and re-run:

```bash
# Override with a different env file entirely
python3 teardown_archive.py path/to/other.env
```

---

## Key talking points

- The application does not need to know which tier a document lives on — the federated endpoint handles routing
- Archived data is still fully queryable; the latency trade-off (2–4 s) is acceptable for infrequently accessed historical records
- Storage cost for the cold tier is significantly lower than keeping all data on a live cluster
- The archive rule can be paused, modified, or deleted at any time; archived data can be restored to the live cluster before teardown
- **Indexes matter on both tiers, but work differently:** a standard MongoDB index on the archive field helps the archive daemon and speeds hot-tier queries; partition fields in the archive rule act as the index for cold storage, letting the federated endpoint skip irrelevant partitions rather than scanning the full archive
- **Schema flexibility requires query awareness:** a small number of documents in `sample_mflix.movies` store `year` as a malformed string (`"1981è"`, `"1994è1998"`) rather than an integer. MongoDB's BSON comparison ordering places all strings after all numbers, so a purely numeric `$lt` filter silently skips those documents — they stay on the hot tier even though they predate the cutoff. The archive query handles this with an `$or` that also matches string-typed `year` values. This is a useful contrast with relational databases, where a typed column prevents mixed types entirely — in MongoDB, heterogeneous field types are valid and the query layer must account for them. Schema validation (`$jsonSchema`) can enforce a single type going forward.
