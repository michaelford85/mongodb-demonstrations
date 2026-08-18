# Atlas → Iceberg (Change Streams Reference Pattern)

A local, repeatable demonstration of a MongoDB Atlas transaction becoming
available in an **Apache Iceberg** table for SQL analytics — using only an
existing Atlas cluster plus local Docker containers. No Snowflake, Databricks,
Confluent Cloud, Kafka SaaS, or cloud object storage required.

> This demo uses MongoDB Atlas Change Streams with local Iceberg infrastructure
> to illustrate a transactional-to-analytical data pattern. **It is not a
> demonstration of MongoDB Atlas Stream Processing, and it does not represent a
> product roadmap commitment.**

---

## Architecture

```
  MongoDB Atlas (cloud)                     Local Docker stack
  ┌──────────────────┐                      ┌───────────────────────────────┐
  │ orders            │  PyMongo Change      │  Python pipeline               │
  │ (transactional)   │  Streams  ────────►  │  (normalize + idempotent write)│
  └──────────────────┘  updateLookup         └───────────────┬───────────────┘
                                                              │ PyIceberg append
                                                              ▼
                              ┌───────────────┐      ┌──────────────────┐
                              │ Iceberg REST  │◄────►│ MinIO (S3 store) │
                              │ catalog       │      │  warehouse/       │
                              └───────┬───────┘      └──────────────────┘
                                      │ metadata
                                      ▼
                              ┌───────────────┐
                              │ Trino (SQL)   │  ← analytical queries
                              └───────────────┘
```

- **MongoDB Atlas** — the transactional source (the only cloud dependency).
- **Python 3.12 pipeline** — PyMongo change stream with `full_document='updateLookup'`,
  writing normalized rows to Iceberg via **PyIceberg** (no Spark writer needed).
- **MinIO** — local S3-compatible object storage.
- **Apache Iceberg REST catalog** — the table metadata catalog.
- **Trino** — the local SQL query engine over the Iceberg table.

No Kafka: a direct Change Streams → Python → Iceberg path is simpler and
sufficient for this demonstration.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker + Docker Compose | Docker Desktop running; ~3 GB free for images |
| Python 3.12 | `python3 --version` |
| An existing MongoDB Atlas cluster | Provisioned via `../atlas-cluster-provisioning` |
| Free local ports | **9000, 9001** (MinIO), **8181** (Iceberg REST), **8080** (Trino) |

### Atlas role / network requirements (no secrets printed)

- Change streams require a **replica set or sharded cluster** — every Atlas
  cluster qualifies. `make check` validates this via the `hello` command.
- The database user needs **read/write on the demo database** (`readWrite` on
  `atlas_iceberg_demo`), or `atlasAdmin` as provisioned by
  `atlas-cluster-provisioning`.
- Your workstation's IP must be on the Atlas **IP Access List**.

---

## Setup

```bash
cd atlas-iceberg-demo
python3 -m pip install -r requirements.txt      # or: make venv
cp .env.example .env
# Edit .env: set MONGODB_URI to the SRV string from atlas-cluster-provisioning.
# The local-infra values (MinIO/Trino/Iceberg) are non-secret defaults — leave as-is.
```

If you provisioned Atlas with the sibling `atlas-cluster-provisioning` project,
you can build `.env` automatically (reuses that project's Terraform output and
DB credentials; no secrets are printed):

```bash
python3 scripts/_build_env_from_provisioning.py
```

`MONGODB_URI`, `DB_NAME`, and `COLLECTION_NAME` follow the same convention as
the `change-streams` and `atlas-databricks-*` demos in this repository.

---

## Run the demonstration

```bash
make up          # 1. start MinIO + Iceberg REST + Trino, wait until healthy
make check       # 1. preflight: Docker, Atlas reachable + change-stream eligible
make seed        # 2. seed historical orders into Atlas (deterministic)
make backfill    # 2. backfill that history into the Iceberg table
make demo        # 3-5. start pipeline, insert one live order, print latency
make query       # 6. analytical SQL: volume + notional value by symbol
make verify-restart  # 7. restart safety — proves no duplicate records
make reset       # 8. remove demo data (Atlas DB, Iceberg table, bucket, state)
make down        #    stop the local infra containers
```

`make start` runs the pipeline in the foreground (Ctrl+C to stop) if you prefer
to drive the live insert yourself in another terminal with
`python3 scripts/live_order.py`.

---

## Expected output (abridged)

`make demo`:

```
════════════════════════════════════════════════════════════════════
  DEMO · live order → Change Streams → Iceberg
════════════════════════════════════════════════════════════════════
pipeline | Watching atlas_iceberg_demo.orders — Ctrl+C to stop.
live-order | Inserted live order  : LIVE-1734000000000
live-order | Atlas insert time    : 2026-08-18T15:04:01.123456+00:00
pipeline | Streamed order LIVE-1734000000000 (BUY MDB x1000) → Iceberg
verify   | Iceberg visible time : 2026-08-18T15:04:03.456789+00:00
verify   | End-to-end latency   : 2.33 seconds
```

`make query` prints total rows, the live order, and volume/notional by symbol.
`make verify-restart` ends with `PASS restart is safe — exactly one copy`.

---

## Idempotency & restart safety

Two independent guarantees keep the demo exactly-once in practice:

1. **Durable resume token.** After every processed event the change-stream
   `_id` is written atomically to `state/resume_token.json` (gitignored). On
   restart the pipeline passes it as `resume_after=`, resuming within Atlas's
   oplog window (24h default) — no missed events.
2. **Dedup-on-write.** Before appending, the writer scans the Iceberg table for
   the batch's `order_id`s and skips any already present. An at-least-once
   replay after an unclean stop therefore never duplicates rows.

`make verify-restart` demonstrates this: it inserts one order, runs the pipeline
twice, and asserts the row count grows by exactly one.

### Event handling

`insert`, `replace`, and full-document `update` events are written as rows
(`updateLookup` supplies the full document). `delete` events are logged as
tombstones but not applied — this demo is append-only. In a production Iceberg
target a delete would be represented either by an equality-delete file (Iceberg
v2 merge-on-read) or by a soft-delete column (e.g. `is_deleted` / `deleted_at`)
carried in the same row, letting analytics filter out removed orders.

---

## Order schema

| Field | Type | Meaning |
|---|---|---|
| `order_id` | string | Unique business key (idempotency key) |
| `account_id` | string | Synthetic account, no PII |
| `symbol` | string | Public ticker (MDB, AAPL, …) |
| `side` | string | BUY / SELL |
| `quantity` | long | Share count |
| `price` | double | Execution price |
| `order_time` | timestamptz | When the order was placed |
| `order_status` | string | NEW / PARTIALLY_FILLED / FILLED / CANCELLED |
| `source_updated_at` | timestamptz | Atlas write time (from the change event) |
| `iceberg_ingested_at` | timestamptz | When the pipeline wrote it to Iceberg |

Data is deterministic synthetic (`random.seed(42)`); no real customer data or PII.

---

## Versions tested

| Component | Version |
|---|---|
| MinIO | `RELEASE.2024-11-07T00-52-20Z` |
| MinIO Client (mc) | `RELEASE.2024-11-05T11-29-45Z` |
| Apache Iceberg REST fixture | `1.9.2` |
| Trino | `468` |
| PyIceberg | `0.8.1` |
| PyMongo | `4.10.1` |
| trino (python) | `0.330.0` |
| Python | `3.12` |

---

## Troubleshooting

**`FAIL Atlas ... not change-stream eligible`** — you are pointed at a
standalone. Use the Atlas SRV string from `atlas-cluster-provisioning`.

**`FAIL Atlas connection`** — check `MONGODB_URI` in `.env` and confirm your IP
is on the Atlas IP Access List.

**Port already in use (8080/8181/9000/9001)** — stop the conflicting service or
change the host port mappings in `docker-compose.yml`.

**Trino "no factory for location" / query errors** — the stack is still
starting. `make up` polls health for up to 120s; re-run `make check`.

**Live order not visible in Iceberg** — ensure the pipeline is running
(`make start` or `make demo`); `verify` polls for up to 90s.

---

## Security notes

- No secrets are committed. `.env` is gitignored; `.env.example` contains
  placeholders only. Resume tokens/checkpoints live under `state/` (gitignored).
- The only cloud dependency is Atlas, reached via `MONGODB_URI`. MinIO/Trino/
  Iceberg credentials are non-secret **local** defaults.
- `reset` drops only this demo's Atlas database (`DB_NAME`) and Iceberg table —
  it never touches other namespaces.

---

## Cleanup

```bash
make reset   # remove demo data (Atlas DB, Iceberg table, bucket objects, state)
make down    # stop infra containers
make clean   # stop infra AND delete the MinIO volume (full local wipe)
```

All cleanup is idempotent and safe to run repeatedly.

---

## Limitations

- Append-only; deletes are logged, not applied (see **Event handling**).
- Single-collection, single-writer pipeline — sized for a demonstration, not a
  production ingest tier.
- Latency depends on your network to Atlas and local Docker performance.
- This is an **integration pattern**, not a MongoDB product feature. No GA,
  preview, or roadmap claim is made or implied.

---

## Real vs illustrative — full disclosure

| Component | Real | Illustrative |
|---|---|---|
| MongoDB Atlas source + change streams | ✅ Real cluster, real change events | — |
| Python pipeline + PyIceberg writes | ✅ Real appends to real Iceberg files | — |
| MinIO / Iceberg REST / Trino | ✅ Real local services in Docker | — |
| Object storage | — | ⚠️ Local MinIO stands in for cloud S3 |
| Delete handling | — | 📖 Documented, not implemented (append-only) |
