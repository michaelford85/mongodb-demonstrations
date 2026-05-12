# Multi-Region Routing: pgvector vs. Atlas Vector Search

Side-by-side demonstration of using two vector stores as the similarity-match
layer in an automated case-routing pipeline. An incoming customer service email
arrives with a (possibly misspelled or partial) account name; the system uses a
fuzzy nearest-neighbour lookup over an account-to-representative table to pick
the correct service agent for the case.

The same synthetic dataset, the same query embeddings, and the same pre-filter
strategy are exercised against both backends so the differences are purely a
property of the database.

## What this demonstrates

1. **Schema flexibility.** Each region (`France`, `Italy`, `Germany`, `Spain`,
   `UK`) carries a different set of regional attributes. Postgres absorbs the
   variability through a single `JSONB` column; MongoDB stores the same data
   as native polymorphic BSON documents in one collection with no migration
   between regional shapes.
2. **Vector search.** Postgres uses `pgvector` with an HNSW cosine index;
   MongoDB uses an Atlas Vector Search index defined in
   `mongodb/atlas_index.json`. Both are queried with the same simulated
   embedding (1024 or 2000 dimensions, shaped like Voyage AI's vectors).
3. **Pre-filtering.** Both queries restrict the candidate set by `region`
   before scoring similarity, which is the cost-saving pattern most teams want
   in production.

> The dataset is fully synthetic. No real customer, company, or person names
> are used anywhere in the code, the generated rows, or this document.

## Repository layout

```
multi-region-rag-eval/
├── compare.py              # run both backends side-by-side
├── config.py               # environment-driven settings
├── embeddings.py           # deterministic stand-in for a hosted embedding API
├── generate_data.py        # synthetic dataset writer (JSONL)
├── postgres/
│   ├── schema.sql          # pgvector DDL (JSONB + vector column + HNSW index)
│   ├── ingest.py           # loader for Amazon RDS Postgres
│   └── search.py           # vector query with region pre-filter
├── mongodb/
│   ├── atlas_index.json    # Atlas Vector Search index definition
│   ├── ingest.py           # loader for MongoDB Atlas
│   └── search.py           # $vectorSearch with region pre-filter
└── data/                   # generated JSONL ends up here
```

## Prerequisites

- Python 3.10 or newer.
- An Amazon RDS / Aurora Postgres instance with the `vector` extension
  installed and a DB user that may create tables/indexes in the target
  database.
- A MongoDB Atlas cluster (M10 or higher for Vector Search) and a DB user with
  read/write access to the target database.
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
  folder's `.env`. You'll still need to create the Atlas Vector Search index
  once, using the definition in `mongodb/atlas_index.json`.

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
#      PG_CONN_STR   — Amazon RDS Postgres connection string
#      MONGO_URI     — MongoDB Atlas connection string
#    The remaining variables (MONGO_DB, MONGO_COLLECTION, PG_TABLE,
#    EMBED_DIM, ROW_COUNT, ATLAS_VECTOR_INDEX) have working defaults and
#    only need to change if your environment differs.
```

The `.env` file is read automatically by `python-dotenv` when any script
starts.

## Step 1 — Generate the synthetic dataset

```bash
python generate_data.py --rows 5000
```

Adjust `--rows` between 1000 and 17000. The output is written to
`data/accounts.jsonl` and includes the per-row embedding so both loaders read
the same vectors.

## Step 2 — Load Postgres (pgvector on Amazon RDS)

```bash
python -m postgres.ingest --truncate
```

The loader executes `postgres/schema.sql` (creating the table, the JSONB GIN
index, and the HNSW cosine index), then bulk-inserts the rows.

## Step 3 — Load MongoDB Atlas

```bash
python -m mongodb.ingest --drop
```

After the load completes, create the Atlas Vector Search index once using the
definition in `mongodb/atlas_index.json` (Atlas UI, `mongosh`, or the Atlas
Admin API). The index name must match `ATLAS_VECTOR_INDEX` in your `.env`, and
`numDimensions` in the index definition must match `EMBED_DIM` (update the
JSON to `2000` if you switched dimensions).

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

Once `.env` is populated and the Atlas Vector Search index has been created,
the following block runs the full pipeline from a clean state and prints a
side-by-side comparison table — useful as a smoke test after any change:

```bash
# From the multi-region-rag-eval directory, with the virtualenv active.
python generate_data.py --rows 5000
python -m postgres.ingest --truncate
python -m mongodb.ingest --drop
python compare.py --query "Auroar Logistcs 4821" --region France
```

Expected signals that the demo is healthy:

- `generate_data.py` prints `Wrote 5000 synthetic rows to data/accounts.jsonl`.
- Each ingest script prints a non-zero total row/document count.
- `compare.py` prints two latency numbers (one per backend) and a single
  results table whose top row from each backend points at the same
  `service_agent_id` for the misspelled query.

## Notes on the embedding stand-in

`embeddings.py` produces deterministic L2-normalised vectors via character
n-gram hashing. This keeps the demo offline and reproducible while still
exhibiting the property the use case relies on: misspellings of the same
string land close together in vector space. Swap in a real embedding provider
by replacing the body of `embed_account` and matching `EMBED_DIM` to the
provider's output dimensionality.

## Environment variables

| Variable              | Purpose                                                |
|-----------------------|--------------------------------------------------------|
| `PG_CONN_STR`         | Postgres connection string (RDS).                      |
| `MONGO_URI`           | MongoDB Atlas connection string.                       |
| `MONGO_DB`            | Target database name in Atlas.                         |
| `MONGO_COLLECTION`    | Target collection name.                                |
| `PG_TABLE`            | Target Postgres table name.                            |
| `EMBED_DIM`           | 1024 or 2000.                                          |
| `ROW_COUNT`           | Default row count for `generate_data.py`.              |
| `ATLAS_VECTOR_INDEX`  | Name of the Atlas Vector Search index.                 |
