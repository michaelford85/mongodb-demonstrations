# Atlas Search Index Build & Load Benchmark

⚠ **Run only against a NON-PRODUCTION test cluster unless an authorized cluster owner has reviewed and explicitly approved the run.** This demo writes synthetic data, creates an Atlas Search index, and generates query/write load.

A repeatable benchmark for a lexical/text Atlas Search workload:

1. **Index build timing** — create a fresh Search index and reach a *verified* ready/queryable state for a known synthetic document count (500K default scenario; 1M sensitivity case).
2. **Search latency/throughput** — under explicit, configurable load profiles.
3. **Optional write churn** — controlled inserts/updates/deletes while search load runs, to observe freshness/latency impact.

Results are kept **separate per phase**. A fresh-index build on a cluster with Dedicated Search Nodes is **not** the same as the Atlas-side DSN transition — see [`DSN_RUNBOOK.md`](./DSN_RUNBOOK.md). This demo never automates or times the DSN transition itself.

## What this demo cannot prove

- Production availability or SLAs.
- Exact three-region / multi-region behavior for your topology.
- The duration of the **Atlas-side Dedicated Search Node (DSN) transition** — that must be separately performed, approved, and timed by an operator ([runbook](./DSN_RUNBOOK.md)).
- Production data-shape fidelity: synthetic documents approximate field counts/types but are not your production data.
- A guaranteed cutover time for anything.

## Planning inputs (unverified — labeled, not treated as truth)

| Input | Status in this demo |
|---|---|
| ~1.2–1.5 KB Search index/doc | Planning estimate only. Validate against **measured** index size (record manually from Atlas UI; never confuse collection storage size with Search index size). |
| 100 Search QPS peak | **Unconfirmed.** Encoded only as the optional, explicitly labeled `stress` profile — not a default, not a requirement. |
| Single-digit current QPS | Encoded as a synthetic **baseline profile of 5 QPS** — labeled synthetic until confirmed. |
| ~2,000 ins / 2,000 del / 500 upd per sec | **Unverified write planning estimates, not Search QPS.** They exceed this demo's hard caps by design. Write rates are opt-in, default **0**. |
| S10 Search tier, three-region Azure | Operator-entered metadata only. Verify region-specific S10 specs and node topology separately. |

The demo uses the **normal Atlas connection and Atlas Search query path** (`$search` via the cluster). It never connects directly to Search Nodes and never calls Atlas admin APIs.

## Prerequisites

- Python 3.10+
- A non-production Atlas cluster where your user can create collections and Search indexes
- PyMongo ≥ 4.7 (search index management API)

```bash
cd atlas-search-index-benchmark
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in; .env is git-ignored
```

### Environment variables (names only — no values here)

| Variable | Purpose |
|---|---|
| `ATLAS_BENCHMARK_URI` | **Required for live phases.** Non-production cluster URI. Never echoed. |
| `ALLOW_ATLAS_BENCHMARK_WRITES` | `true` to opt in to writes/index/load. Default `false`. |
| `BENCHMARK_CONFIRM` | `yes` to confirm the printed sanitized preview. Default `no`. |
| `ATLAS_BENCHMARK_DB` / `ATLAS_BENCHMARK_COLLECTION` | Demo-owned namespace (default `search_bench_demo.bench_docs`). Never point at production/business data. |
| `ATLAS_BENCHMARK_INDEX_NAME` | Search index name (default `bench_lexical_index`). |
| `ATLAS_BENCHMARK_INDEX_DEFINITION` | Optional local JSON file with your **actual** Search index definition (preferred for meaningful measurements). |
| `DOC_COUNT`, `BATCH_SIZE`, `GENERATOR_SEED` | Seed phase knobs. |
| `LOAD_QPS`, `LOAD_WARMUP_SECONDS`, `LOAD_DURATION_SECONDS`, `LOAD_CONCURRENCY`, `LOAD_QUERY_TIMEOUT_SECONDS` | Load profile. |
| `MIXED_INSERT_PER_SEC`, `MIXED_UPDATE_PER_SEC`, `MIXED_DELETE_PER_SEC` | Optional write churn; default 0 (off). |
| `MIXED_TTL_SIMULATION` | `none` (default) or `delete_only`. This demo **never creates a TTL index**; TTL-like behavior is simulated with deletes only, and only if you opt in. |
| `CLUSTER_LABEL`, `SEARCH_NODE_TIER`, `SEARCH_NODE_TOPOLOGY` | Manual metadata recorded in results. Never inferred from the URI. |
| `ATLAS_BENCHMARK_REGIONS` | Comma-separated region names (e.g. `region1,region2,region3`) — operator-entered, verified in Atlas; never inferred. |
| `SEARCH_NODE_COUNT` | Operator-entered Search Node count/topology; never inferred. |
| `INDEX_VALIDATION_WINDOW_SECONDS` | Sustained-validation window before the index phase reports `ready` (default 30). |

### Hard safety caps

`DOC_COUNT ≤ 2,000,000`, `LOAD_QPS ≤ 100`, `LOAD_CONCURRENCY ≤ 64`, `LOAD_DURATION_SECONDS ≤ 7200`, write rates ≤ 500/250/250 ops-sec (ins/upd/del), `BATCH_SIZE ≤ 5000`. Invalid or over-cap values are refused at startup. Caps live in `config.py` (`HARD_LIMITS`); raise them **deliberately** by editing that file after review — not via env.

### Triple opt-in for anything live

1. `ATLAS_BENCHMARK_URI` set (non-production)
2. `ALLOW_ATLAS_BENCHMARK_WRITES=true`
3. `BENCHMARK_CONFIRM=yes`, plus an interactive `CONFIRM` after the sanitized preview (or `BENCHMARK_ASSUME_YES=true` for CI)

The preview prints **only** host labels and the namespace — never credentials or the full URI.

## Usage

```bash
# 1) Plan-only (default; no writes, no network):
python benchmark.py            # or: python benchmark.py plan

# 2) Small smoke test — after filling .env and opting in via env vars:
DOC_COUNT=5000 LOAD_DURATION_SECONDS=15 \
ALLOW_ATLAS_BENCHMARK_WRITES=true BENCHMARK_CONFIRM=yes python benchmark.py seed
ALLOW_ATLAS_BENCHMARK_WRITES=true BENCHMARK_CONFIRM=yes python benchmark.py index
ALLOW_ATLAS_BENCHMARK_WRITES=true BENCHMARK_CONFIRM=yes python benchmark.py load

# 3) 500K scenario:
DOC_COUNT=500000 python benchmark.py plan   # review, then run seed/index/load as above

# 4) 1M sensitivity case:
DOC_COUNT=1000000 python benchmark.py plan

# 5) Optional stress profile (explicitly labeled; unverified planning input):
LOAD_QPS=100 LOAD_CONCURRENCY=32 LOAD_DURATION_SECONDS=120 \
ALLOW_ATLAS_BENCHMARK_WRITES=true BENCHMARK_CONFIRM=yes python benchmark.py load

# 6) Optional mixed workload (opt-in, capped; defaults are 0):
MIXED_INSERT_PER_SEC=50 MIXED_UPDATE_PER_SEC=25 MIXED_DELETE_PER_SEC=10 \
ALLOW_ATLAS_BENCHMARK_WRITES=true BENCHMARK_CONFIRM=yes python benchmark.py mixed

# 7) Cleanup — opt-in, previewed, limited to the demo namespace only:
ALLOW_ATLAS_BENCHMARK_WRITES=true BENCHMARK_CONFIRM=yes python benchmark.py cleanup
```

Ctrl-C stops load generators cleanly; partial results/metadata are still written.

## Output

Each phase writes `results/<phase>-<ts>.json` (machine-readable) and a matching `.md` summary. Included: UTC start/end + elapsed for seeding and create-to-verified-ready; offered vs achieved QPS; success/error/timeout counts; latency p50/p90/p95/p99; index definition file + hash; generator seed; runtime versions; operator-entered tier/topology metadata.

**Measured vs operator-recorded:** Search index size, per-region readiness, Search Node CPU/storage, and index freshness/lag are **not** exposed by the driver API used here. They are listed in results as operator-recorded metrics with the Atlas UI location to read them (Cluster → **Search** tab index metrics). Do not substitute collection storage size. The DSN runbook template captures these per region.

## Readiness semantics and evidence categories (DSN-aware runs)

The `index` phase reports **distinct milestones**, never collapsed:

1. **Create request accepted** — timestamp + request round-trip.
2. **Documented index state transitions** — `status` (`PENDING`/`BUILDING`/`READY`) and `queryable` from `list_search_indexes` (driver API; see [PyMongo Collection API](https://pymongo.readthedocs.io/en/stable/api/pymongo/collection.html) and [Manage Search indexes](https://www.mongodb.com/docs/atlas/atlas-search/manage-indexes/)).
3. **First successful representative `$search` query** — through the normal cluster connection.
4. **Sustained validation** — representative queries must keep succeeding for the whole `INDEX_VALIDATION_WINDOW_SECONDS` window; only then does the phase report `ready`.

Evidence categories, kept separate:

- **Index state** — from the documented driver API (`status`, `queryable`).
- **Query succeeded through tested route** — proves only that the tested route served the query at that moment. It does **not** prove readiness on every Search Node or in every region.
- **Per-node/per-region readiness** — **not available via supported automation in this demo.** The MongoDB driver exposes index-level state only; this demo deliberately does not call Atlas Admin APIs, so per-node health is recorded as `not_available_via_supported_automation` with per-region operator-evidence fields (fill in only what the [Atlas UI Search tab / monitoring](https://www.mongodb.com/docs/search/deployment/monitoring/) or Support actually shows). A cluster-level READY state is never treated as proof that every DSN is healthy.

## What this demo cannot prove

- Production availability or SLAs, or a guaranteed cutover time for anything.
- Readiness on **every** DSN/region unless directly verified by a supported source (see above).
- Exact three-region behavior for your topology.
- DSN migration duration from a fresh index build — fresh builds and the [DSN migration](https://www.mongodb.com/docs/search/deployment/deployment-options/) are different operations ([runbook](./DSN_RUNBOOK.md)).
- Production data-shape fidelity: synthetic documents approximate field counts/types but are not your production data.

## Results template for MongoDB Support

`results/*.json` already contain: sanitized cluster label, namespace, index name + definition hash, generator seed, runtime/driver versions, operator-entered tier/regions/node count, per-phase UTC timestamps/elapsed, offered/achieved QPS + latency percentiles, milestone timings, sustained-validation result, per-node/per-region status (`not_available_via_supported_automation` + operator evidence fields), and limitation notes. Add manually from Atlas UI: Search index size (index metrics, not collection storage), per-node/per-region observations, and Search Node CPU/storage. Never include credentials or full URIs.

## Run matrix

| Scenario | `DOC_COUNT` | `LOAD_QPS` | Writes | Purpose |
|---|---|---|---|---|
| Smoke | 5,000 | 5 (baseline, synthetic) | off | validate pipeline end-to-end |
| 500K baseline | 500,000 | 5 | off | primary index-build + load data |
| 1M baseline | 1,000,000 | 5 | off | scale sensitivity |
| 500K stress | 500,000 | 100 (unverified planning peak) | off | headroom check |
| 500K mixed | 500,000 | 5 | opt-in, ≤ caps | freshness/latency interaction |

**None of these rates or the future write estimates (2000/2000/500) are approved production requirements.**

## Cleanup

`python benchmark.py cleanup` previews exactly what will be removed — the demo Search index and the demo collection **only**. It never drops a database, never touches other namespaces, and never alters cluster/tier/DSN/project settings. Manual leftover checks: Atlas UI → Search tab (index gone) and Browse Collections (collection gone).

## Known limitations

- Latency is measured client-side over the normal cluster path; internal Search Node timing is not exposed.
- Index size is not reported by the driver API used here — record it manually (see Output).
- The default `search_index.default.json` is an **illustrative lexical mapping**, explicitly not equivalent to any production mapping. Supply `ATLAS_BENCHMARK_INDEX_DEFINITION` for meaningful numbers.
- Seeding resumability (skip-existing) is automatic for ≤100K docs; for larger runs re-running continues by deterministic `_id` sequence, and the count confirmation in results catches gaps.
- Write churn exercises plain inserts/updates/deletes only; no TTL index is ever created.

## Tests (offline, no Atlas credentials)

```bash
python -m pytest tests/ -v
```

## References (verified reachable MongoDB documentation)

- Atlas Search overview: https://www.mongodb.com/docs/atlas/atlas-search/
- Manage Search indexes (create/poll/drop): https://www.mongodb.com/docs/atlas/atlas-search/manage-indexes/
- `$search` pipeline: https://www.mongodb.com/docs/atlas/atlas-search/query-syntax/
- Deployment options incl. Dedicated Search Nodes: https://www.mongodb.com/docs/search/deployment/deployment-options/
- Monitoring Search: https://www.mongodb.com/docs/search/deployment/monitoring/
- PyMongo search index management: https://pymongo.readthedocs.io/en/stable/api/pymongo/collection.html
