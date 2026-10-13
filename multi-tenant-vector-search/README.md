# Multi-Tenant Vector Search — match the index to the tenant, not the other way round

A runnable reproduction of the [recommended Atlas multi-tenant vector search
architecture](https://www.mongodb.com/docs/vector-search/deployment/multi-tenant-architecture/):
**one shared flat index** for the long tail of small tenants, plus a **dedicated
HNSW index on a per-tenant View** for each large tenant. Both are queried with
the same `$vectorSearch` API — a tiny router (`lib/router.py`) picks the right
one from the `tenant_id`, so application code never changes.

| Regime | Tenant shape | Index | Lives on | Query-time pre-filter |
|--------|--------------|-------|----------|-----------------------|
| **Small tenants** (the many) | < ~10k vectors each, always filtered to one tenant | **Flat** (`indexingMethod: "flat"`) | the **shared base collection** | `tenant_id` equality filter |
| **Large tenants** (the few) | big partitions, higher QPS | **HNSW** (the default) | a **View per tenant** (`$match` + `$expr`) | none — the view is already scoped |

**Why two shapes?** An HNSW graph is built *without* the filter, so a highly
selective `tenant_id` filter on a shared HNSW index makes queries traverse the
whole graph and recall collapses. A **flat** index instead does an exhaustive
scan of just the filtered partition — exact and cheap when each partition is
small. Large partitions are the opposite case: too big to scan every query, and
big enough that a dedicated graph pays for itself. So the small tenants share
one flat index and each large tenant gets its own HNSW index on a view. The demo
loads a corpus with both kinds of tenant and lets you see the trade-off directly
with `scripts/benchmark.py`.

---

## Prerequisites

- Python 3.11+
- A MongoDB Atlas cluster provisioned by [`../atlas-cluster-provisioning`](../atlas-cluster-provisioning)
  with **Search Nodes enabled** (vector search on views is served by `mongot`).
- `mongosh` installed locally, to follow along in the shell.
- *(Optional)* A [Voyage AI](https://www.voyageai.com) API key for **real**
  embeddings. Every script also accepts `--fake-embeddings`, which generates
  deterministic offline vectors so you can exercise the full topology — indexes,
  views, routing, latencies — with no key and no embedding cost. (Recall is only
  meaningful with real embeddings.)

> This demo assumes the cluster already exists. It only loads data, creates the
> views and search indexes, and queries them. It creates **no** Atlas resources
> until you run the scripts yourself.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env: paste your cluster's SRV string into MONGODB_URI and add your
# DB_ADMIN_USER / password (from the atlas-cluster-provisioning output).
# (Optional) set VOYAGE_API_KEY for real embeddings — skip it if you use
# --fake-embeddings everywhere. PROFILE=demo is a good starting point.
```

Every name the demo uses — database, collection, both index names, and the view
prefix — lives in `.env`, so the setup scripts, the router, and the `mongosh`
snippets below all stay in sync. Change a name in one place and everything else
follows.

### 3. Load the multi-tenant corpus

```bash
python scripts/load_data.py                          # PROFILE from .env, real embeddings
python scripts/load_data.py --fake-embeddings        # no Voyage key/cost
python scripts/load_data.py --profile scale --fake-embeddings --drop
```

The `demo` profile loads a few thousand documents across **12 small tenants**
(`small_0000` … `small_0011`) and **2 large tenants** (`globex`, `initech`),
all into one base collection with a `tenant_id` field. The `scale` profile
crosses the ~10k-vectors-per-tenant line where a dedicated HNSW index clearly
wins — pair it with `--fake-embeddings` to avoid a large embedding bill.

### 4. Create the shared flat index and the per-tenant HNSW views

```bash
python scripts/create_indexes.py --profile demo
```

This creates, idempotently:

- **`shared_flat_index`** — a `vectorSearch` index with `indexingMethod: "flat"`
  on the base collection, plus a `filter` on `tenant_id`. Serves every small
  tenant.
- for each large tenant, a **view** (`tenant_view_<id>`, defined as
  `$match` + `$expr` on `tenant_id`) and a default **HNSW** `vectorSearch` index
  (`tenant_hnsw_index`) built directly on that view.

### 5. Confirm every index is READY

Atlas builds indexes asynchronously. Wait 1–2 minutes, then:

```bash
python scripts/status.py --profile demo
```

Re-run until the flat index and every large-tenant HNSW index report `READY`.
You can watch the same thing in the Atlas UI under **Search Indexes**.

### 6. Query as any tenant — routing is automatic

```bash
python scripts/query.py "reset my password" --tenant small_0003
python scripts/query.py "migrate data between regions" --tenant globex
```

`query.py` prints how the request was routed before showing results — a small
tenant hits `shared_flat_index` with a `tenant_id` pre-filter; a large tenant
hits its own `tenant_hnsw_index` view with no filter. Add `--fake-embeddings`
if you loaded the data that way, so the query vector matches the stored vectors.

### 7. See why one index does not fit every regime

```bash
python scripts/benchmark.py --profile demo --iterations 20
```

For each large tenant this runs the same query two ways over the same vectors —
the shared **flat** index (filtered) versus the tenant's dedicated **HNSW**
view — and reports median latency and the HNSW top-k overlap with the exact flat
result. That is the whole thesis in one table: flat is exact and fine for small
partitions, HNSW earns its place as the partition grows.

When you are done, `scripts/teardown.py` drops every index and view (and, with
`--drop-data`, the collection).

---

## Scripts

| Script | What it does |
|--------|--------------|
| `scripts/load_data.py` | Generates the synthetic multi-tenant corpus, embeds it (Voyage or `--fake-embeddings`), and inserts it into the base collection. |
| `scripts/create_indexes.py` | Creates the shared flat index, and a View + HNSW index for each large tenant. Idempotent. |
| `scripts/status.py` | Document counts plus the build status of the flat index and every large-tenant HNSW index. |
| `scripts/query.py` | Routes and runs a `$vectorSearch` for one tenant, printing which index served it. |
| `scripts/benchmark.py` | Flat-vs-HNSW latency and recall comparison for the large tenants. |
| `scripts/teardown.py` | Drops the indexes and views (add `--drop-data` to drop the collection too). |

---

## Follow along in mongosh

Everything the scripts do is plain MongoDB — here is the same thing by hand.
Connect once, then paste. `<vector>` is a query embedding (1024 floats for
`voyage-3.5`); in the demo you generate it with `query.py`, but the shapes below
are exactly what the scripts issue.

```bash
mongosh "$MONGODB_URI"
```

```javascript
use multi_tenant_vector_search
```

### The shared flat index (small tenants)

```javascript
db.documents.createSearchIndex(
  "shared_flat_index",
  "vectorSearch",
  { fields: [
      { type: "vector", path: "embedding", numDimensions: 1024,
        similarity: "cosine", indexingMethod: "flat" },
      { type: "filter", path: "tenant_id" }
  ] }
)
```

A small tenant's query is a normal `$vectorSearch` **with a `tenant_id`
pre-filter** — the flat index then scans only that tenant's partition:

```javascript
db.documents.aggregate([
  { $vectorSearch: {
      index: "shared_flat_index",
      path: "embedding",
      queryVector: <vector>,
      filter: { tenant_id: { $eq: "small_0003" } },
      limit: 10 } },
  { $project: { _id: 0, doc_id: 1, tenant_id: 1, category: 1,
                score: { $meta: "vectorSearchScore" } } }
])
```

### A large tenant's dedicated HNSW view

Vector search on a view supports only `$match`+`$expr`, `$addFields`, and
`$set`, so the tenant filter is expressed with `$expr`:

```javascript
db.createView(
  "tenant_view_globex",
  "documents",
  [ { $match: { $expr: { $eq: ["$tenant_id", "globex"] } } } ]
)

db.tenant_view_globex.createSearchIndex(
  "tenant_hnsw_index",
  "vectorSearch",
  { fields: [
      { type: "vector", path: "embedding", numDimensions: 1024,
        similarity: "cosine", indexingMethod: "hnsw" }
  ] }
)
```

The large tenant's query targets the **view** and needs **no filter** — the view
already contains only that tenant's documents, so the HNSW graph is tenant-pure:

```javascript
db.tenant_view_globex.aggregate([
  { $vectorSearch: {
      index: "tenant_hnsw_index",
      path: "embedding",
      queryVector: <vector>,
      numCandidates: 200,
      limit: 10 } },
  { $project: { _id: 0, doc_id: 1, tenant_id: 1, category: 1,
                score: { $meta: "vectorSearchScore" } } }
])
```

---

## Architecture

```
lib/tenants.py  (synthetic corpus: many small tenants + a few large ones)
    ↓ scripts/load_data.py   (embeds via lib/embeddings.py → Voyage or fake)
MongoDB Atlas  (multi_tenant_vector_search.documents  — one tenant_id per doc)
    ↓ scripts/create_indexes.py
    ├── shared_flat_index         (vectorSearch, indexingMethod: flat, filter: tenant_id)
    │      └── serves every SMALL tenant, pre-filtered by tenant_id
    └── for each LARGE tenant:
           tenant_view_<id>       (view: $match + $expr on tenant_id)
             └── tenant_hnsw_index (vectorSearch, indexingMethod: hnsw, no filter)

lib/router.py
    route(tenant_id) → small ? (documents, shared_flat_index, +filter)
                     : large ? (tenant_view_<id>, tenant_hnsw_index, no filter)
    used by scripts/query.py and scripts/benchmark.py
```

---

## Notes

- **Why client-side embeddings?** The same `embedding` field has to be visible
  to the flat index *and* to every view, and query vectors must match the stored
  ones — so the demo embeds client-side (`lib/embeddings.py`) and stores the
  vector on each document. `--fake-embeddings` swaps in deterministic offline
  vectors so the topology and latencies are real without a key or a bill.
- **Flat is a pre-filter story.** A flat index is only the right call for small
  tenants *because every query carries a `tenant_id` filter*. Drop the filter
  and you scan every tenant — never query the flat index without it.
- **Views must be `$match`+`$expr`.** Vector search on a view supports only
  `$match` wrapping `$expr`, `$addFields`, and `$set` — no `$lookup`. The scripts
  use exactly `{$match: {$expr: {$eq: ["$tenant_id", "<id>"]}}}`.
- **Where the regime line sits.** MongoDB's guidance is ~10k vectors per tenant:
  below it, flat; above it, a dedicated HNSW index. The `scale` profile crosses
  that line so `benchmark.py` shows the crossover; the `demo` profile stays small
  so a full real-embedding run is quick and cheap.
