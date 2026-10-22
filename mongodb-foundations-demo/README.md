# MongoDB Foundations: Live Walkthrough

A local, presenter-driven Streamlit app for a 90-minute MongoDB foundations
session with database architects who have deep Oracle/RDBMS experience.

**This app is designed to be run against an Atlas-hosted cluster, but it teaches
general MongoDB concepts.** Nothing in the seven sections is Atlas-specific;
Atlas is the demo environment, and the separate live-metrics walkthrough at the
end is the only Atlas-specific part of the session.

It is an education session, not a product pitch. Every write is explicit,
isolated to one synthetic namespace, and reversible.

**Industry-agnostic by design.** The dataset is a set of customers, the accounts
they hold, and a ledger of dated, categorised entries — a shape that recurs in
every vertical, so no example depends on one. Every name is invented and every
counterparty uses the reserved `Example …` convention; no real organisation is
referenced anywhere in the demo.

---

## What it demonstrates

| Section | Content |
|---|---|
| ① Document model & data modeling | One customer document, the relational→document mapping, why some data is embedded and some referenced, and the `$jsonSchema` validators the server enforces |
| ② Querying & aggregation | A projected `find` on nested fields, and a `$match`/`$group` pipeline — each with the query shown, a result table, and the SQL intent |
| ③ Indexes & query behaviour | The index list, a query shaped for a compound index, and `explain` in execution-stats mode |
| ④ Transactions & consistency | An isolated, idempotent multi-document transfer with preview, confirmation, and reset |
| ⑤ Replica sets — an overview | Replica-set vocabulary mapped to relational terms, plus a read-only deployment summary (`hello`, driver topology, `replSetGetStatus` and `replSetGetConfig` when authorized) and a clearly labelled sharding callout |
| ⑥ High availability & MongoDB | Live election state, the driver's durability settings, a failure-scenario table, and how write concern, read preference, and retryable writes decide what the application experiences |
| ⑦ Monitoring handoff | The signals to inspect in any monitoring tool, then the handoff to Atlas |

### Optional Search & AI add-on (sections ⑧–⑨)

Sections ①–⑦ are the core foundations session. Sections ⑧–⑨ are a self-contained
add-on for the "MongoDB Search and how it fits into RAG" conversation. They use
one extra collection, `knowledge_chunks`, in the same demo database, with their
own seed and their own Atlas Search indexes.

| Section | Content |
|---|---|
| ⑧ MongoDB Search | One query, four strategies over the same chunked corpus: full-text (BM25 `$search`), semantic (`$vectorSearch` on an `autoEmbed` index), hybrid (`$rankFusion`), and AI retrieval (hybrid + a Voyage AI reranker). Each result set ships with the exact aggregation as a copy-pasteable `mongosh` snippet |
| ⑨ Search for RAG | MongoDB as the retrieval half of RAG: a question becomes retrieved grounding, then a grounded prompt, then an optional generated, citeable answer. Retrieval and the prompt always run; generation is optional |

**Automated Embedding.** The vector index is declared as `autoEmbed`, so Atlas
generates embeddings at index time and query time using a Voyage AI model. The
app never computes an embedding — semantic and hybrid queries pass plain text.

**Everything AI is optional and key-gated.** Full-text, semantic, and hybrid
search need no extra keys. The AI reranker needs `VOYAGE_API_KEY`; the RAG
answer step needs `GEN_API_KEY`. Without them, the sections still demonstrate
the MongoDB-powered retrieval and show the exact prompt.

Deliberately out of scope in the core sections ①–⑦: Atlas Search, Vector Search,
geospatial, `$graphLookup`, time series, and anything sharding-related beyond
the callout. Search and Vector Search are covered only in the ⑧–⑨ add-on.

---

## Prerequisites

- **Python 3.10+** (3.11 recommended) and a virtual environment
- An existing **replica-set** MongoDB deployment. The cluster from
  [`../atlas-cluster-provisioning`](../atlas-cluster-provisioning) is the
  intended environment. This project never provisions anything and never runs
  Terraform.
- A database user with **`readWrite`** on `mongodb_foundations_demo`
  (the `readWriteAnyDatabase` app user from `atlas-cluster-provisioning` works).
- **Atlas IP access:** your current IP must be on the project's IP access list
  (Atlas → Network Access), otherwise the connection times out.

---

## Install and run

```bash
cd mongodb-foundations-demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set MONGODB_URI to your cluster's SRV connection string.
```

`MONGODB_URI` is the only variable the app reads. `.env` is git-ignored and no
credential, connection string, or secret is ever printed by the app or the
scripts.

```bash
python3 scripts/status.py      # verify readiness from the command line
python3 seed_data.py           # seed the dedicated demo database
streamlit run app.py           # http://localhost:8501
```

---

## Seed and reset

Everything lives in one database: **`mongodb_foundations_demo`**, in
three collections — `customers`, `accounts`, `transactions`. No other namespace
is read or written, and every destructive helper asserts the target database name
before it runs.

Nothing is written when the app starts. Seeding and resetting are always
explicit, confirmed actions.

| Action | Where | Effect |
|---|---|---|
| Seed | **Demo Readiness** page → `Seed demo data` → `Confirm`, or `python3 seed_data.py` | Drops the three collections, recreates them with their schema validators, rebuilds them from the deterministic seed, then creates the indexes |
| Reset demo data | Sidebar (every page) → `Reset demo data` → `Confirm` | Full re-seed back to the exact seed state |
| Reset transaction demo only | Sidebar, or section ④ | Restores the two demo balances and deletes only the ledger entries flagged `demo_transfer: true` |
| Remove entirely | `python3 teardown.py` | Drops the demo database and frees port 8501 |

The dataset is small and seeded from fixed values (12 customers, 22 accounts,
240 transactions), so a reset takes a second and always produces identical
documents.

### Indexes this demo creates

Five, each tied to an access pattern shown in the session (plus the automatic
`_id_` on each collection).

| Collection | Index | Serves |
|---|---|---|
| `customers` | `{ "preferences.contact_channel": 1, "address.state": 1 }` | Section ② — filter on a nested preference and nested geography |
| `accounts` | `{ "account_number": 1 }` (unique) | Sections ① and ④ — account lookup and the transaction's balance updates |
| `accounts` | `{ "customer_id": 1 }` | Section ① — resolve a customer's referenced accounts |
| `transactions` | `{ "account_number": 1, "posted_at": -1 }` | Section ③ — the compound-index / `explain` query |
| `transactions` | `{ "category": 1, "posted_at": -1 }` | Section ② — the `$match`/`$group` aggregation |

### Schema validation this demo applies

Each collection is created with a `$jsonSchema` validator, so the rules are
enforced by the server on every insert and update — not by the application. The
seed itself is inserted through those rules. Section ① shows each validator in
full and lets the presenter attempt a deliberately invalid insert and watch the
server reject it with error code `121`.

| Collection | Level / action | Rules |
|---|---|---|
| `customers` | `strict` / `error` | `customer_id`, `name`, `segment`, `address`, `contact` required; `segment` and `preferences.contact_channel` restricted to a list; `address.state` two capitals; `recent_notices` capped at 3 |
| `accounts` | `strict` / `error` | `account_number`, `customer_id`, `account_type`, `status`, `currency`, `balance` required; `balance` numeric and ≥ 0; `account_type`, `status`, `currency` restricted to a list |
| `transactions` | `moderate` / `error` | `txn_id`, `account_number`, `category`, `direction`, `amount`, `posted_at` required; `amount` > 0; `direction` is `debit` or `credit`; `posted_at` must be a date |

`transactions` is deliberately `moderate` so both validation levels appear on
screen: `strict` validates every write, `moderate` exempts documents that
already violate the rules when they are updated. Fields the validator does not
mention are still allowed, and rules are changed with `collMod` — a metadata
change, not a table rewrite.

---

## Search & RAG add-on (sections ⑧–⑨)

Optional and self-contained. It adds one collection, `knowledge_chunks`, to the
same `mongodb_foundations_demo` database, seeded from invented, industry-neutral
knowledge articles that the demo chunks at seed time — the same way a real RAG
pipeline chunks its sources.

```bash
pip install -r requirements.txt          # pulls the optional voyageai/openai too
python3 seed_search.py                    # chunk + seed knowledge_chunks
python3 scripts/create_search_indexes.py  # create the two Atlas Search indexes
python3 scripts/search_status.py          # wait until both indexes are READY
```

| Action | Where | Effect |
|---|---|---|
| Seed corpus | Section ⑧/⑨ → `Seed search corpus now`, or `python3 seed_search.py` | Drops and rebuilds only `knowledge_chunks` from the deterministic chunker |
| Create indexes | Section ⑧/⑨ → `Create search indexes now`, or `python3 scripts/create_search_indexes.py` | Creates the BM25 and `autoEmbed` vector indexes (built asynchronously by Atlas) |
| Check status | `python3 scripts/search_status.py` | Corpus count, per-index READY/building, and whether the optional keys are set |

The two Atlas Search indexes on `knowledge_chunks`:

| Index | Type | Serves |
|---|---|---|
| `knowledge_text_index` | Atlas Search (BM25) | Full-text search on the chunk `text` |
| `knowledge_vector_index` | Vector Search (`autoEmbed`) | Semantic and hybrid search — Atlas embeds text with a Voyage AI model at index and query time |

Index builds are asynchronous; allow a minute or two after creation before the
sections become queryable. The sections guard on both prerequisites and offer an
in-app button when either is missing.

---

## Presenter runbook (5–10 minutes end to end)

Turn **Presenter mode** on in the sidebar: minimal prose, large output. Turn it
off to reveal the full written explanation on any page.

1. **① Document model** (2 min) — pick a customer, read the document aloud, then
   the relational→document table. Deliver the cue: *model from access patterns —
   what is read and written together?* Show the embedded contact/preferences and
   the referenced accounts, and say plainly that embedding is a choice, not a
   default. Then scroll to the schema-validation block: show the live
   level/action table, open one validator, and press `Attempt the invalid
   insert` so the audience sees the server reject the write. Land the cue:
   *schema-less does not mean rule-less.*
2. **② Querying & aggregation** (90s) — Example 1: pick a channel and a state,
   `Run example`, point at the query above the table, give the one-line SQL
   intent. Example 2: `Run example`, note that `$match` comes first so an index
   can reduce the working set before grouping.
3. **③ Indexes & explain** (2 min) — show the index list, then the query shaped
   like the compound index. `Run query`, then `Run explain`. Compare *documents
   examined* against *documents returned* in both columns. Say that indexes buy
   read efficiency with write and storage overhead, and that these numbers are
   this run, not a benchmark.
4. **④ Transaction** (2 min) — `Preview transaction` first, so the audience sees
   the three operations before anything is written. Then `Run transaction` →
   confirm. Show before/after balances and the new ledger entry. Land the three
   facts: single-document writes are atomic; multi-document transactions exist
   for invariants that span documents; this replica set supports them. Then
   `Reset demo data`.
5. **⑤ Replica sets** (90s) — start with the vocabulary table: primary/standby,
   oplog/redo, election/failover, majority/quorum. Then the replica-set name,
   the connected member's role, members as the driver sees them, and the voting
   configuration. Read the sharding callout verbatim and be explicit that it
   does not describe this cluster.
6. **⑥ High availability** (2 min) — show the election term and majority size,
   then the driver's own durability settings. Walk the failure-scenario table
   row by row, and land the point that the topology provides availability while
   write concern, read preference, and retryable writes decide what the
   application actually experiences. Close with what HA does *not* cover:
   replication is not backup.
7. **⑦ Monitoring handoff** (60s) — the signals, then the cue: *next, switch to
   Atlas to show these same concepts as live metrics.* Leave the app and drive
   Atlas directly.

---

## Troubleshooting

**Connection times out / `ServerSelectionTimeoutError`**
Almost always the IP access list. Add your current IP in Atlas → Network Access.
Also confirm `MONGODB_URI` is the SRV string for a running cluster.

**`Missing configuration` banner**
`.env` does not exist or `MONGODB_URI` is unset. `cp .env.example .env` and set
it, then reload the page.

**Authentication or authorization failure**
The user exists but lacks rights on the demo database. Use a user with
`readWrite` on `mongodb_foundations_demo`. The **Demo Readiness**
page reports the connected user's roles under `Database permissions`.

**`No demo data yet`**
Seed it: **Demo Readiness** → `Seed demo data` → `Confirm`, or
`python3 seed_data.py`.

**`replSetGetStatus` or `replSetGetConfig` not available**
Expected with a least-privilege user. Section ⑤ falls back to `hello` and driver
metadata and says so on screen, and section ⑥ hides only the election panel.
`clusterMonitor` (or `atlasAdmin`) enables the member-status, member-configuration,
and election tables.

**Transaction errors**
Multi-document transactions require a replica set or a sharded deployment —
section ④ checks this and disables the run button if unavailable. A
`TransientTransactionError` or timeout during an election is surfaced as a clear
message; the demo data is left unchanged, and `Reset demo data` restores the
seed state either way.

**`Document failed validation` (error code 121)**
Expected in section ① when the invalid-insert button is pressed — that is the
demonstration. Anywhere else it means a document no longer satisfies its
collection's validator in `lib/schema.py`; adjust the validator or the seed data
in `lib/sample_data.py`, then re-seed.

**Port 8501 already in use**
`python3 teardown.py --keep-db` frees the port, or run
`streamlit run app.py --server.port 8502`.

---

## Files

| File | Purpose |
|---|---|
| `app.py` | Landing page: title, subtitle, the seven section cards, running order |
| `pages/1_…` – `7_…` | The seven independent sections |
| `pages/8_Demo_Readiness.py` | The seven readiness checks, plus confirmed seeding |
| `seed_data.py` | Deterministic seed + validators + index creation from the command line |
| `teardown.py` | Drops the demo database and frees the Streamlit port |
| `scripts/status.py` | The readiness checks as CLI output |
| `lib/mongo_client.py` | Cached client, the demo namespace constants, timeouts |
| `lib/sample_data.py` | The deterministic synthetic dataset |
| `lib/seed.py` | Guarded seed / index / reset helpers |
| `lib/schema.py` | The `$jsonSchema` validators and the rejected-write example |
| `lib/queries.py` | Prebuilt query, aggregation, index, and `explain` helpers |
| `lib/transactions.py` | The isolated multi-document transfer |
| `lib/deployment.py` | Read-only `hello` / topology / `replSetGetStatus` / `replSetGetConfig` / driver-durability introspection |
| `lib/readiness.py` | The readiness checks |
| `lib/ui.py` | Shared chrome: guards (incl. the Search/RAG prerequisites), presenter mode, tables, confirmed reset |
| `pages/9_MongoDB_Search.py` | ⑧ Full-text, semantic, hybrid, and AI-retrieval search over the chunked corpus |
| `pages/10_Search_for_RAG.py` | ⑨ Retrieval-augmented generation: retrieve → ground → prompt → optional answer |
| `seed_search.py` | Chunk and seed `knowledge_chunks` from the command line |
| `scripts/create_search_indexes.py` | Create the BM25 and `autoEmbed` Atlas Search indexes |
| `scripts/search_status.py` | Corpus / index / optional-key readiness for the Search & RAG add-on |
| `lib/search_config.py` | Search & RAG namespace constants and the optional Voyage/LLM clients |
| `lib/search_data.py` | The invented source articles and the deterministic chunker |
| `lib/search_seed.py` | Guarded seed / drop for `knowledge_chunks` |
| `lib/search_index.py` | Create / status / drop for the two Atlas Search indexes |
| `lib/search.py` | The four search strategies, each returning results + the exact pipeline |
| `lib/explain.py` | Renders a pipeline as a copy-pasteable `mongosh` snippet with stage notes |
| `lib/rag.py` | Retrieve → grounded context → prompt → optional generation |
| `.env.example` | `MONGODB_URI` (core), plus the optional Search/RAG keys and knobs |

---

## Safety

- All data is synthetic and invented for this demo. No customer data, no PII, no
  real records, no production-like credentials.
- The app reads only `MONGODB_URI` and never prints it. Readiness reports
  presence, not value.
- Reads and writes are confined to `mongodb_foundations_demo`; the
  seed, reset, and teardown helpers refuse to run against any other database.
- No infrastructure is created or modified. No Terraform is executed, and no
  Atlas resource is touched.
