# Multi-Region Routing: pgvector vs. Atlas Vector Search

Side-by-side demonstration of using two vector stores as the similarity-match
layer in an automated case-routing pipeline. An incoming customer service email
arrives with a (possibly misspelled or partial) account name; the system uses a
fuzzy nearest-neighbour lookup over an account-to-representative table to pick
the correct service agent for the case.

The same synthetic dataset, the same Voyage AI embedding model, and the same
pre-filter strategy are exercised against both backends so the differences
are purely a property of the database.

## What this demonstrates

1. **Schema flexibility.** Each region (`France`, `Italy`, `Germany`, `Spain`,
   `UK`) carries a different set of regional attributes. Postgres absorbs the
   variability through a single `JSONB` column; MongoDB stores the same data
   as native polymorphic BSON documents in one collection with no migration
   between regional shapes.
2. **Vector search with real embeddings.** Both backends embed text with
   [Voyage AI](https://docs.voyageai.com/) using the same model (configured
   via `VOYAGE_MODEL`). Postgres uses `pgvector` with an HNSW cosine index
   over a client-side embedding; MongoDB uses an Atlas Vector Search index
   with `type: "autoEmbed"`, so Atlas generates and maintains the vectors
   server-side from the document text — no application code touches a query
   vector.
3. **Pre-filtering.** Both queries restrict the candidate set by `region`
   before scoring similarity, which is the cost-saving pattern most teams want
   in production.

> The dataset is fully synthetic. No real customer, company, or person names
> are used anywhere in the code, the generated rows, or this document.

## Repository layout

```
multi-region-rag-eval/
├── compare.py              # run both backends side-by-side
├── cleanup.py              # wipe data from both clusters in one shot
├── config.py               # environment-driven settings
├── embeddings.py           # Voyage AI client wrapper (batching + retries)
├── generate_data.py        # synthetic dataset writer (JSONL + embeddings)
├── postgres/
│   ├── schema.sql          # pgvector DDL (JSONB + vector column + HNSW index)
│   ├── ingest.py           # loader for Amazon RDS Postgres
│   ├── cleanup.py          # truncate or drop the routing table
│   └── search.py           # vector query with region pre-filter
├── mongodb/
│   ├── atlas_index.json    # Atlas Vector Search index definition (autoEmbed)
│   ├── create_index.py     # apply atlas_index.json to the Atlas cluster
│   ├── ingest.py           # loader for MongoDB Atlas
│   ├── cleanup.py          # delete documents or drop the collection
│   └── search.py           # $vectorSearch with region pre-filter
└── data/                   # generated JSONL ends up here
```

## Prerequisites

- Python 3.10 or newer.
- An Amazon RDS / Aurora Postgres instance with the `vector` extension
  installed and a DB user that may create tables/indexes in the target
  database.
- A MongoDB Atlas cluster (M10 or higher for Vector Search) and a DB user with
  read/write access to the target database. Atlas Automated Embedding requires
  a cluster running MongoDB 8.1+ on a tier that supports Vector Search.
- A [Voyage AI](https://docs.voyageai.com/) API key with quota for the model
  configured in `VOYAGE_MODEL`. The same key is used client-side by the
  Postgres path and server-side by Atlas Automated Embedding.
- Network reachability from the machine running the scripts to both clusters.

### Provisioning the backing clusters

This folder assumes the two clusters already exist, but two sibling projects
in this repository can stand them up for you with a single command each:

- **Aurora PostgreSQL + pgvector** — see
  [`../postgres-cluster-provisioning`](../postgres-cluster-provisioning).
  Its Terraform creates the cluster, opens the security group to your IP, and
  installs the `vector` extension declaratively. After `./setup.sh` finishes,
  run `terraform output -raw connection_string` to get the value you should
  paste into `PG_CONN_STR` in this folder's `.env`.
- **MongoDB Atlas cluster + DB user** — see
  [`../atlas-cluster-provisioning`](../atlas-cluster-provisioning). Its
  Terraform creates an `mongodbatlas_advanced_cluster` and an `atlasAdmin`
  database user inside an existing Atlas project. After `./deploy.sh`
  finishes, copy the connection string it prints into `MONGO_URI` in this
  folder's `.env`. The Atlas Vector Search index itself is still created
  from this folder via `python -m mongodb.create_index` (see Step 3 below).

Skipping the provisioning helpers and pointing at clusters you already manage
works exactly the same — only `PG_CONN_STR` and `MONGO_URI` matter to the
scripts here.

## Setup

A template environment file is provided at `.env.example`. Copy it to `.env`
and fill in the actual values for your clusters — `.env` itself is gitignored
so no credentials are committed.

```bash
cd multi-region-rag-eval
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Copy the template:
cp .env.example .env

# 2. Open .env in your editor and set, at minimum:
#      PG_CONN_STR     — Amazon RDS Postgres connection string
#      MONGO_URI       — MongoDB Atlas connection string
#      VOYAGE_API_KEY  — Voyage AI API key
#    The remaining variables (MONGO_DB, MONGO_COLLECTION, PG_TABLE,
#    VOYAGE_MODEL, EMBED_DIM, ROW_COUNT, ATLAS_VECTOR_INDEX) have working
#    defaults and only need to change if your environment differs.
```

The `.env` file is read automatically by `python-dotenv` when any script
starts.

## Step 1 — Generate the synthetic dataset

```bash
python generate_data.py --rows 5000
```

Adjust `--rows` between 1000 and 17000. The output is written to
`data/accounts.jsonl`. Each row carries both the composed `embedding_text`
(used by Atlas Automated Embedding) and the Voyage AI vector produced from
that text (used by the Postgres path), so both loaders share an embedding
space.

## Step 2 — Load Postgres (pgvector on Amazon RDS)

```bash
python -m postgres.ingest --truncate
```

The loader executes `postgres/schema.sql` (creating the table, the JSONB GIN
index, and the HNSW cosine index), then bulk-inserts the rows.

## Step 3 — Load MongoDB Atlas and create the Vector Search index

```bash
python -m mongodb.ingest --drop
python -m mongodb.create_index --wait
```

The ingest stores the raw `embedding_text` only; Atlas generates and maintains
the vectors server-side once the index is created with `type: "autoEmbed"`.

`mongodb/create_index.py` reads `mongodb/atlas_index.json`, substitutes
`${VOYAGE_MODEL}` with the value from `.env`, and creates the index (or
updates it in place if it already exists). Pass `--wait` to block until the
index reports `queryable=true`, `--replace` to drop and recreate it, and
`--timeout SECONDS` to extend the default 600 s wait.

## Step 4 — Run a fuzzy lookup

A representative inbound email might contain `"Auroar Logistcs 4821"` instead
of the true account name `"Aurora Logistics 4821"`. Either backend can be
queried directly:

```bash
python -m postgres.search --query "Auroar Logistcs 4821" --region France
python -m mongodb.search  --query "Auroar Logistcs 4821" --region France
```

Or run both at once and print a comparison table:

```bash
python compare.py --query "Auroar Logistcs 4821" --region France
```

Drop `--region` to perform a global search across all regions and observe the
latency difference from skipping the pre-filter.

## End-to-end verification

Once `.env` is populated, the following block runs the full pipeline from a
clean state and prints a side-by-side comparison table — useful as a smoke
test after any change:

```bash
# From the multi-region-rag-eval directory, with the virtualenv active.
python generate_data.py --rows 5000
python -m postgres.ingest --truncate
python -m mongodb.ingest --drop
python -m mongodb.create_index --wait
python compare.py --query "Auroar Logistcs 4821" --region France
```

Expected signals that the demo is healthy:

- `generate_data.py` prints `Wrote 5000 synthetic rows to data/accounts.jsonl`.
- Each ingest script prints a non-zero total row/document count.
- `mongodb.create_index --wait` ends with `Index 'accounts_vector_idx' is queryable.`
- `compare.py` prints two latency numbers (one per backend) and a single
  results table whose top row from each backend points at the same
  `service_agent_id` for the misspelled query.

## Cleaning up the data

Three scripts are provided to remove the demo data; each prompts for
confirmation before doing anything destructive. Pass `--yes` to skip the
prompt in automation.

```bash
# Wipe both clusters at once (TRUNCATE + delete_many({}); keeps schema,
# indexes, the pgvector extension, and the Atlas Vector Search index).
python cleanup.py

# Or target a single backend:
python -m postgres.cleanup
python -m mongodb.cleanup

# Remove the table and the collection entirely. Dropping the collection
# also drops any Atlas Vector Search indexes attached to it, so you will
# need to rerun `python -m mongodb.create_index --wait` before the next
# search.
python cleanup.py --drop
python -m postgres.cleanup --drop-table
python -m mongodb.cleanup  --drop
```

These scripts touch only the routing-demo objects named by `PG_TABLE`,
`MONGO_DB`, and `MONGO_COLLECTION` in your `.env`. The pgvector extension
itself is left installed; remove it (and the underlying clusters) using the
sibling provisioning projects' `teardown.sh` scripts.

## Embeddings

Both backends embed text with [Voyage AI](https://docs.voyageai.com/) using
the model named in `VOYAGE_MODEL`. The two paths differ only in *where* the
embedding call happens:

- **Postgres path.** `generate_data.py` and `postgres/search.py` call the
  Voyage AI API client-side (see `embeddings.py`), then hand the resulting
  vector to `pgvector` for storage and `<=>` cosine search. Voyage's
  recommended `input_type` is set per call (`document` for ingest, `query`
  for search) and `output_dimension` is passed through for the models that
  support flexible Matryoshka dimensions (`voyage-3-large`, the `voyage-4-*`
  family).
- **MongoDB path.** `mongodb/ingest.py` stores only the raw `embedding_text`.
  The Atlas Vector Search index, created with `type: "autoEmbed"` and the
  same `VOYAGE_MODEL`, generates and maintains vectors server-side. At query
  time, `mongodb/search.py` passes the query text under
  `$vectorSearch.query.text` and Atlas embeds it with the same model before
  scoring — no application code ever holds the query vector.

The two paths share an embedding space because they share a model, so
results between the backends are directly comparable.

## Environment variables

| Variable              | Purpose                                                |
|-----------------------|--------------------------------------------------------|
| `PG_CONN_STR`         | Postgres connection string (RDS).                      |
| `MONGO_URI`           | MongoDB Atlas connection string.                       |
| `MONGO_DB`            | Target database name in Atlas.                         |
| `MONGO_COLLECTION`    | Target collection name.                                |
| `PG_TABLE`            | Target Postgres table name.                            |
| `VOYAGE_API_KEY`      | Voyage AI API key (client-side + Atlas autoEmbed).     |
| `VOYAGE_MODEL`        | Voyage AI embedding model (e.g. `voyage-3-large`).     |
| `EMBED_DIM`           | Vector dimensions: 256, 512, 1024, or 2048.            |
| `ROW_COUNT`           | Default row count for `generate_data.py`.              |
| `ATLAS_VECTOR_INDEX`  | Name of the Atlas Vector Search index.                 |
