# pdf-rag-eval — Cosmos DB vs MongoDB Atlas, fed by PDFs in Azure Blob

This folder is a side-by-side RAG comparison between **Azure Cosmos DB
for NoSQL** (DiskANN vector index) and **MongoDB Atlas Vector Search**,
using a synthetic PDF corpus stored in Azure Blob Storage and Voyage AI
embeddings (`voyage-4-large` at 1024 dims).

## Why this matters

Each comparison demo is designed to surface a concrete operational difference between the two backends. The table below maps demos to outcomes.

| Demo | Cosmos behaviour | Atlas behaviour | Operational outcome |
|---|---|---|---|
| `compare/connections` | RU ceiling enforced via gateway queueing — appears as p99 latency by default; `--surface-throttles` exposes the 429s the SDK was hiding | Handles concurrent load without throttling | Higher query concurrency without scaling RUs (or building bespoke retry logic to mask throttles) |
| `compare/full_scan` | High RU cost per full-container scan | Low-latency indexed scan | Large catalogs searchable without partition exhaustion |
| `compare/batch_throughput` | At `--rows 10000 --workers 8`: ~13% of writes and ~96% of queries are throttled with `--surface-throttles`; without it the throttling is hidden as 4-5× slower writes and a 90× drop in query throughput | Bulk ops complete predictably at 10k–50k rows | Large batch files process end-to-end without rate limiting or hidden retry tax |
| `compare/index_limits` | Rejects >1 vector path per container | Accepts multiple vector indexes on one collection | Multiple embedding fields (e.g. description + attributes) can coexist |
| `compare/product_match` | Cross-partition fan-out adds latency; result varies with partition pressure | Consistent low-latency ranked results | Similarity search is predictable under load |
| `retrieve.py` | N/A | Atlas as metadata directory; PDF stays in Blob | Unstructured documents retrievable without copying into the DB |

## Pipeline (current state)

```
generate_pdfs.py     →  data/source_pdfs/*.pdf  +  data/pdf_manifest.jsonl
upload_blobs.py      →  Azure Blob container (manifest gets blob_url)
embed_and_load.py    →  data/chunks.jsonl  (Voyage embeddings included)
cosmos/ingest.py     →  Cosmos DB NoSQL container
mongodb/ingest.py    →  MongoDB Atlas collection
mongodb/create_index.py → Atlas Vector Search index
compare/*.py         →  Cosmos-vs-Atlas comparison demos
retrieve.py          →  query → Atlas vector search → SAS-signed PDF URL
```

## Prerequisites

| Component | How to get it |
|---|---|
| Cosmos DB account with vector container | Run `../cosmosdb-cluster-provisioning/setup.sh`. The vector policy must be set at container creation, so this **cannot** be created from this folder. |
| MongoDB Atlas cluster | M10+ for Vector Search. Point `MONGODB_URI` at it. |
| Azure Blob storage account | `cd infra && ./setup.sh` (within this folder). |
| Voyage AI API key | https://www.voyageai.com — paste into `.env`. |

## One-time setup

```bash
cd pdf-rag-eval
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Provision the blob storage account.
cd infra
cp .env.example .env
$EDITOR .env            # ARM_SUBSCRIPTION_ID, TF_VAR_storage_account_name, allow-list IP
./setup.sh

# Pull the storage connection string into the parent .env so the Python
# scripts can use it (terraform output -raw avoids echoing the key).
STORAGE_CONN_STR="$(terraform output -raw connection_string)"
cd ..
cp .env.example .env
$EDITOR .env            # VOYAGE_API_KEY, COSMOS_ENDPOINT, COSMOS_KEY, MONGODB_URI
echo "AZURE_STORAGE_CONNECTION_STRING=$STORAGE_CONN_STR" >> .env
```

Cosmos endpoint and key come from the sibling demo:

```bash
( cd ../cosmosdb-cluster-provisioning && \
  echo "COSMOS_ENDPOINT=$(terraform output -raw endpoint)" >> ../pdf-rag-eval/.env && \
  echo "COSMOS_KEY=$(terraform output -raw primary_key)"   >> ../pdf-rag-eval/.env )
```

## Run the pipeline

The fastest path is the bootstrap script, which runs every step below in
order, validates `.env`, wipes stale data, and verifies that both
backends hold the same chunk count and the Atlas index is queryable
before exiting:

```bash
./bootstrap.sh                  # full pipeline + verification
./bootstrap.sh --with-smoke     # also run product_match + batch_throughput smoke tests
./bootstrap.sh --skip-clean     # keep existing data/ artifacts
```

The manual sequence (what `bootstrap.sh` invokes) is:

```bash
python generate_pdfs.py             # ~20 PDFs in data/source_pdfs/
python upload_blobs.py --overwrite  # uploads to Azure Blob, updates manifest
python embed_and_load.py            # extracts, chunks, embeds → data/chunks.jsonl
python -m cosmos.ingest             # upserts into Cosmos
python -m mongodb.ingest --drop     # inserts into Atlas
python -m mongodb.create_index --wait
```

> **Atlas Auto Embeddings (optional):** If source documents change frequently, consider enabling [Atlas Auto Embeddings](https://www.mongodb.com/docs/atlas/atlas-vector-search/auto-embeddings/) on the collection instead of re-running `embed_and_load.py` manually. When a watched field changes, Atlas automatically recomputes the embedding and updates the vector index. This demo uses manual embedding for portability and to keep both backends on identical vectors; Auto Embeddings is the recommended path for high-churn production catalogs.

`data/chunks.jsonl` is the single source of truth that both backends
ingest from — guaranteeing they hold byte-identical chunk text and
Voyage vectors so the upcoming comparison demos score the same pairs on
each side.

## Document shape (both stores)

```json
{
  "chunk_id":    "8b4f..._p007_c003",
  "document_id": "8b4f1c2a9e10",
  "blob_path":   "catalog/spec-8b4f1c2a9e10.pdf",
  "blob_url":    "https://<account>.blob.core.windows.net/pdfs/...",
  "filename":    "spec-8b4f1c2a9e10.pdf",
  "title":       "Product Specification Sheet: ...",
  "vendor":      "Acme Industries",
  "category":    "storage-hardware",
  "item_id":     "ACM-19284-M",
  "revision":    "2025-11-04",
  "page_number": 7,
  "chunk_index": 3,
  "text":        "...",
  "embedding":   [0.012, ...]   // 1024 floats from voyage-4-large
}
```

Mongo uses `_id = chunk_id`; Cosmos uses `id = chunk_id` and partitions
on `/document_id` so every chunk of the same PDF lands in one logical
partition (deliberately, for the partition-ceiling demo in 2c).

## Configuration knobs

All in `.env`:

| Variable | Default | Notes |
|---|---|---|
| `VOYAGE_MODEL` | `voyage-4-large` | Any flexible-dim Voyage model. |
| `EMBED_DIM` | `1024` | 256 / 512 / 1024 / 2048. Must match the Cosmos vector policy and Atlas index. |
| `COSMOS_DATABASE` | `ragdb` | Override only if you changed the Terraform default. |
| `COSMOS_CONTAINER` | `chunks` | Same. |
| `MONGO_DB` | `pdf_rag_eval` | Atlas database name. |
| `MONGO_COLLECTION` | `chunks` | Atlas collection name. |
| `ATLAS_VECTOR_INDEX` | `chunks_vector_idx` | Name in `mongodb/atlas_index.json`. |
| `AZURE_STORAGE_CONTAINER` | `pdfs` | Blob container name. |
| `PDF_COUNT` | `20` | Number of synthetic PDFs. |
| `CHUNK_CHAR_SIZE` | `1500` | Character window per chunk. |
| `CHUNK_CHAR_OVERLAP` | `200` | Must be < `CHUNK_CHAR_SIZE`. |

> Changing `EMBED_DIM` requires recreating the Cosmos container (the
> vector policy is immutable) **and** updating `numDimensions` in
> `mongodb/atlas_index.json` before running `create_index.py --replace`.

## Teardown

```bash
# Atlas: drop the collection or remove the search index.
python -c "from pymongo import MongoClient; from config import load_settings; \
s=load_settings(); MongoClient(s.mongo_uri)[s.mongo_db][s.mongo_collection].drop()"

# Blob storage + resource group:
cd infra && ./teardown.sh

# Cosmos:
cd ../../cosmosdb-cluster-provisioning && ./teardown.sh
```

## Comparison demos (`compare/`)

Each script can be pointed at one backend or both. They expect the
pipeline above to have run, so both stores hold the same chunks and the
Atlas Vector Search index is queryable.

```bash
# Concurrent vector-search load. At the defaults (--workers 16 --top-k 5)
# a small corpus stays under the 1000 RU/s autoscale floor and no
# throttling appears -- the interesting datapoint is the throughput and
# latency gap between the two backends at the same concurrency.
python -m compare.connections --workers 16 --duration 30

# --ru-stress preset (--workers 64 --top-k 50) combines higher concurrency
# with a more expensive scan per query so per-query RU x rps comfortably
# exceeds the Cosmos ceiling. By default the azure-cosmos SDK auto-retries
# 429s for up to 30s, so saturation shows up as inflated p99 latency
# rather than throttled requests. Add --surface-throttles to disable the
# SDK auto-retry and let 429s land in the 'throttled' column directly.
python -m compare.connections --ru-stress --duration 30
python -m compare.connections --ru-stress --surface-throttles --duration 30

# Vector-paths-per-container cap. Tries Cosmos with 11 vector paths
# (rejected), then creates 11 vectorSearch indexes on a temporary Atlas
# collection (accepted) and tears them down.
python -m compare.index_limits

# Cost of scan-style operations. Cosmos RU per page vs Atlas latency
# for total count and full _id projection across the chunk set.
python -m compare.full_scan

# Batch write + query throughput. Submits --rows synthetic documents in bulk,
# then hammers both backends with concurrent vector searches for --duration
# seconds. As with `connections`, the azure-cosmos SDK auto-retries 429s by
# default so throttling shows up as inflated p99/op-rate rather than in the
# throttled column; add --surface-throttles to disable the SDK auto-retry.
python -m compare.batch_throughput --rows 10000 --workers 8 --duration 30
python -m compare.batch_throughput --rows 10000 --surface-throttles
python -m compare.batch_throughput --rows 50000 --only atlas

# Side-by-side product description match. Embeds the query with Voyage AI and
# returns ranked results from both backends with similarity scores and latency.
python -m compare.product_match "portable power supply 12V industrial grade"
python -m compare.product_match "safety data sheet flammable solvent" --category compliance --k 3
```

All accept `--only cosmos` or `--only atlas` if you want to drive
one side at a time.

## Metadata-driven retrieval (`retrieve.py`)

Demonstrates the "MongoDB as the directory of your unstructured data"
story: the chunk's vector lives in Atlas, the authoritative PDF stays
in Blob, and Atlas's metadata is the join key. The script never copies
the PDF into the database — it mints a short-lived SAS URL on demand.

```bash
# Top-5 hits, with SAS URLs valid for 15 minutes.
python retrieve.py "what are the safety procedures"

# Push the category filter into the $vectorSearch stage (pre-filter,
# not post-filter) and save just the matching page of each hit locally.
python retrieve.py "flammable solvent handling" --category compliance --save-pages out/

# Shorter-lived URLs for a live demo.
python retrieve.py "rack installation checklist" --k 3 --expiry 5
```

Each result prints the rank, similarity score, title, page number,
category, item_id, vendor, the chunk_id, a one-line text snippet, and
a signed URL. With `--save-pages DIR`, the script downloads each hit's
PDF from Blob, slices out the specific page via `pypdf`, and writes it
as `NN-<filename-stem>-pPPP.pdf` so you can hand a reviewer the exact
page that was retrieved rather than the whole document.
