# Demo script: MongoDB Atlas Vector Search vs Azure Cosmos DB for NoSQL

Personal reference — not for commit. ~30 min walkthrough.

## Pre-demo checklist (run 10 min before)

```bash
cd pdf-rag-eval && source .venv/bin/activate

# Sanity: both stores have the chunks, Atlas index is queryable.
python -c "from pymongo import MongoClient; from config import load_settings; \
s=load_settings(); print('Atlas:', MongoClient(s.mongo_uri)[s.mongo_db][s.mongo_collection].count_documents({}))"
python -c "from cosmos.client import get_container; from config import load_settings; \
s=load_settings(); c=get_container(s); \
print('Cosmos:', list(c.query_items('SELECT VALUE COUNT(1) FROM c', enable_cross_partition_query=True))[0])"

# Smoke-test the retrieve path so you know SAS URLs work.
python retrieve.py "rollout checklist" --k 1
```

Capture the real RU numbers from `compare/full_scan.py` once so you can quote them if asked.

---

## Framing (2 min)

> "Same PDFs, same Voyage embeddings, same chunks — `data/chunks.jsonl` feeds both stores byte-for-byte. Anything different we see is the store, not the data."

Open the pipeline diagram in `README.md`. Point out that both ingest paths read the same JSONL.

---

## 1. `retrieve.py` — the architectural picture (5 min)

```bash
python retrieve.py "what does the compliance team need for an audit" --k 3
```

Click the first SAS URL → browser opens the source PDF directly from Blob, no credential prompt.

**Talking points:**
- Atlas brokered query → vector → metadata → blob in one step.
- The PDF is **not in the database**. Blob is the source of truth, Atlas is the directory.
- SAS URL expires in 15 minutes (configurable). The storage account key never leaves the client.

Then re-run with the filter:

```bash
python retrieve.py "audit evidence" --department compliance --k 3
```

> "`--department` is pushed into `$vectorSearch.filter`, so Atlas restricts the candidate set **before** HNSW traversal — that's a pre-filter, not a post-filter. The `filter`-typed fields are declared in `mongodb/atlas_index.json`."

---

## 2. `compare/full_scan.py` — cost of touching all the data (5 min)

```bash
python -m compare.full_scan
```

**Land the point:**
- RU column on Cosmos sums `x-ms-request-charge` per page across the scan.
- Atlas reports latency only — no per-operation billing unit.
- "RAG isn't just embed-and-search. Re-embedding when the model changes, eval harnesses, deduping, freshness checks — all scan. On Cosmos every one of those is RU."

If asked about Cosmos cost: the autoscale floor is **1000 RU/s minimum**, so you pay for that floor even when idle.

---

## 3. `compare/index_limits.py` — cost of evolving the schema (5 min)

```bash
python -m compare.index_limits
```

**Land the point:**
- Cosmos vector paths cap at **10 per container** and the vector policy is **immutable after creation**.
- Atlas accepted all 11 `vectorSearch` indexes on a single collection; practical cap is in the thousands per cluster.
- "Want to A/B two embedding models? Layer hybrid keyword + vector? Onboard a tenant on a different model? On Atlas that's an index create. On Cosmos that's a new container and full re-ingest."

---

## 4. `compare/connections.py` — operational headroom (5 min)

```bash
# Start gentle to show the shape.
python -m compare.connections --workers 4 --duration 10

# Then crank it.
python -m compare.connections --workers 16 --duration 30
```

**Watch the `throttled` column climb on Cosmos.** Frame as:
- Cosmos: vector queries are billed in RU. Burst above the autoscale ceiling → 429s.
- Atlas: vector search isn't per-request billed; concurrency is gated by tier connection limits, not by a per-query budget.
- "You don't have to forecast RU/s consumption per vector query and bake it into capacity planning."

---

## 5. Architectural close (5 min) — the unstated benefits

Pull these up only if there's time / interest. Each one came out of actually building the demo, not from marketing material:

1. **Cosmos `id` rejects `/`, `\`, `?`, `#`.** Hit it on first upsert; had to redesign `chunk_id`. `embed_and_load.py` carries the comment.
2. **Immutable vector policy.** Show `cosmos/client.py` — it deliberately refuses to auto-create the container to make this impact visible.
3. **Logical-partition ceiling (20 GB / 10k RU per partition-key value).** Partitioning on `/document_id` means one very large document is a planning problem.
4. **Two Terraform providers needed for Cosmos vector setup** — `azurerm` for the container, `azapi` with raw JSON for `vectorEmbeddingPolicy` and DiskANN `vectorIndex` (azurerm hasn't shipped those yet — `hashicorp/terraform-provider-azurerm#29597`). Atlas Vector Search index is one JSON file submitted through the standard driver.
5. **Autoscale floor: 1000 RU/s minimum.** Below that you're manually provisioned.

---

## What this demo does NOT prove (say it before they ask)

- **Not a recall@k comparison.** Same vectors on both sides → identical retrieval quality by construction. Real DiskANN vs HNSW quality differences only show up well past this corpus size.
- **Not a $/month comparison.** RU vs M-tier pricing is workload-shaped. `full_scan.py` shows *how* the cost models differ, not the bottom line.
- **Not a p99-at-scale benchmark.** 121 chunks is a feature-completeness demo. For 100M-vector tail-latency answers, they need a different harness.

---

## If asked

| Question | Short answer |
|---|---|
| "Why not use Cosmos MongoDB API?" | Different product; this comparison is specifically NoSQL/DiskANN, which is what Azure positions against Atlas Vector Search. |
| "What about Cosmos's `VectorDistance` ORDER BY?" | We use it — see `compare/connections.py`. Throttling happens regardless of query shape once RU budget is exceeded. |
| "Can Atlas do hybrid (vector + BM25)?" | Yes, `$rankFusion` / `$search` + `$vectorSearch` in one pipeline. Not in this demo but easy to add. |
| "Is the SAS URL secure enough?" | Read-only, time-bounded (default 15 min, override with `--expiry`), single-blob scope. Account key parsed locally, never sent. |
| "What if our PDFs are in S3, not Blob?" | Swap `azure-storage-blob` for `boto3`; the Atlas side is unchanged. That's the point — Atlas is the directory, not the store. |
