# MongoDB Foundations: Live Walkthrough

A local, presenter-driven Streamlit app for a 90-minute MongoDB foundations
session with database architects who have deep Oracle/RDBMS experience.

**This app is designed to be run against an Atlas-hosted cluster, but it teaches
general MongoDB concepts.** Nothing in the six sections is Atlas-specific; Atlas
is the demo environment, and the separate live-metrics walkthrough at the end is
the only Atlas-specific part of the session.

It is an education session, not a product pitch. Every write is explicit,
isolated to one synthetic namespace, and reversible.

---

## What it demonstrates

| Section | Content |
|---|---|
| ① Document model & data modeling | One customer document, the relational→document mapping, why some data is embedded and some referenced, and the `$jsonSchema` validators the server enforces |
| ② Querying & aggregation | A projected `find` on nested fields, and a `$match`/`$group` pipeline — each with the query shown, a result table, and the SQL intent |
| ③ Indexes & query behaviour | The index list, a query shaped for a compound index, and `explain` in execution-stats mode |
| ④ Transactions & consistency | An isolated, idempotent multi-document transfer with preview, confirmation, and reset |
| ⑤ Replica sets, resilience & scale | A read-only deployment summary (`hello`, driver topology, `replSetGetStatus` when authorized) and a clearly labelled sharding callout |
| ⑥ Monitoring handoff | The three signals to inspect in any monitoring tool, then the handoff to Atlas |

Deliberately out of scope: Atlas Search, Vector Search, geospatial,
`$graphLookup`, time series, and anything sharding-related beyond the callout.

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
| `customers` | `strict` / `error` | `customer_id`, `name`, `segment`, `address`, `contact` required; `segment` and `preferences.contact_channel` restricted to a list; `address.state` two capitals; `recent_alerts` capped at 3 |
| `accounts` | `strict` / `error` | `account_number`, `customer_id`, `account_type`, `status`, `currency`, `balance` required; `balance` numeric and ≥ 0; `account_type`, `status`, `currency` restricted to a list |
| `transactions` | `moderate` / `error` | `txn_id`, `account_number`, `category`, `direction`, `amount`, `posted_at` required; `amount` > 0; `direction` is `debit` or `credit`; `posted_at` must be a date |

`transactions` is deliberately `moderate` so both validation levels appear on
screen: `strict` validates every write, `moderate` exempts documents that
already violate the rules when they are updated. Fields the validator does not
mention are still allowed, and rules are changed with `collMod` — a metadata
change, not a table rewrite.

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
5. **⑤ Replica set** (90s) — replica-set name, connected member's role, members
   as the driver sees them. Read the sharding callout verbatim and be explicit
   that it does not describe this cluster.
6. **⑥ Monitoring handoff** (60s) — the three signals, then the cue: *next,
   switch to Atlas to show these same concepts as live metrics.* Leave the app
   and drive Atlas directly.

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

**`replSetGetStatus` not available**
Expected with a least-privilege user. Section ⑤ falls back to `hello` and driver
metadata and says so on screen. `clusterMonitor` (or `atlasAdmin`) enables the
member-status table.

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
| `app.py` | Landing page: title, subtitle, the six section cards, running order |
| `pages/1_…` – `6_…` | The six independent sections |
| `pages/7_Demo_Readiness.py` | The seven readiness checks, plus confirmed seeding |
| `seed_data.py` | Deterministic seed + validators + index creation from the command line |
| `teardown.py` | Drops the demo database and frees the Streamlit port |
| `scripts/status.py` | The readiness checks as CLI output |
| `lib/mongo_client.py` | Cached client, the demo namespace constants, timeouts |
| `lib/sample_data.py` | The deterministic synthetic dataset |
| `lib/seed.py` | Guarded seed / index / reset helpers |
| `lib/schema.py` | The `$jsonSchema` validators and the rejected-write example |
| `lib/queries.py` | Prebuilt query, aggregation, index, and `explain` helpers |
| `lib/transactions.py` | The isolated multi-document transfer |
| `lib/deployment.py` | Read-only `hello` / topology / `replSetGetStatus` summary |
| `lib/readiness.py` | The readiness checks |
| `lib/ui.py` | Shared chrome: guards, presenter mode, tables, confirmed reset |
| `.env.example` | `MONGODB_URI` only |

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
