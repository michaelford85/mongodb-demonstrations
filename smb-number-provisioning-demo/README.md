# SMB Number Provisioning Demo

A presenter-ready Streamlit walkthrough of an **SMB telephone-number
provisioning flow** on a document database: the account supplies its own
numbers, they enter through three routes (portal UI, batch CSV, direct API),
all funnelling into **one shared validation + cap-enforcement service**, with
per-account capacity enforced by an atomic conditional counter update and a
`PROVISIONING_REJECTED` audit trail.

Everything here is **synthetic demo data**: brands, accounts, and telephone
numbers are invented (numbers use the reserved fictional range
`+1 (555) 555-xxxx`). No real company, customer, or personal data is
used, and the demo performs **no real verification or vetting** — vetting is
shown as a conceptual step only.

    streamlit run app.py

## Pages

| Page | What it demonstrates |
|---|---|
| **Overview** (`app.py`) | The flow: account supplies numbers → three entry routes → conceptual vetting → per-account cap check → accepted asset or `422` rejection. Notes the open SMB deployment decision. |
| **① Ingest numbers** | Portal single entry, CSV batch upload (file order, per-row results, downloadable sample CSV), direct-API JSON simulation, and reactivation/transfer examples. All routes call the same `process_ingest` service, so enforcement cannot diverge. |
| **② Concurrency race** | The repeatable 99-of-100 race: two concurrent one-number requests, exactly one succeeds, one gets `422 SERVICE_PACKAGE_CAP_EXCEEDED`. |
| **③ Schema & indexes** | Readable JSON for `accounts` and `numberAssets`, the unique asset index, the recommended counter schema, and confirmed-vs-proposed labelling. |
| **④ Results & audit** | Capacity usage, audit events (including `PROVISIONING_REJECTED` examples), cap-lowering, removal, and a targeted, confirm-gated cleanup. |
| **⑤ Architecture considerations** | Shared workload context, the out-of-scope robocall-mitigation workload, the open isolation decision, and the runtime atomicity strategy. |

## Setup

```bash
cd smb-number-provisioning-demo
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit .env from your approved local secret source
streamlit run app.py
```

### Environment variables (names only — never commit values)

| Variable | Purpose |
|---|---|
| `MONGODB_URI` | Connection string for an existing cluster. Read only from this folder's `.env`, never printed, logged, or shown in the UI. |
| `DEMO_DATABASE` | Dedicated demo database. Default `smb_number_demo`. The connection string's own default database is **never** used. |
| `STREAMLIT_SERVER_PORT` | Optional. Defaults to Streamlit's usual port. |

## Safety model

- **Scope:** reads and writes are confined to the `DEMO_DATABASE` database
  (default `smb_number_demo`) and its four collections: `accounts`,
  `numberAssets`, `provisioningCounters`, `provisioningAudit`.
- **No writes on startup.** Seeding and every scenario run only when you
  press a button. Seeding is idempotent (`$setOnInsert` upserts) and never
  drops or overwrites anything.
- **No destructive operations.** No database or collection drops, no deletes
  of anything other than this demo's own synthetic records (targeted cleanup
  on the Results page, behind an explicit confirmation checkbox).
- **No secrets in UI/logs.** The connection string is never displayed or
  logged; error surfaces show exception types only.
- **Idempotent writes.** Every ingestion request carries an idempotency key;
  a retry replays prior per-item outcomes instead of duplicating assets or
  double-counting capacity.

## Inspecting results in the database console

Connect to the same cluster with your database console and open the database
named on every page header (`smb_number_demo` unless you set
`DEMO_DATABASE`). Useful checks:

```js
use smb_number_demo
db.accounts.find({ accountId: "ACC-SMB-0001" })
db.numberAssets.find({}, { tn: 1, state: 1, channel: 1 }).limit(20)
db.numberAssets.getIndexes()      // unique: { accountId, "tn.orig.startTn", type }
db.provisioningCounters.find()    // demo/design recommendation
db.provisioningAudit.find().sort({ at: -1 }).limit(10)
```

Every document carries `"note": "synthetic demo data"` so you can always tell
demo records from anything else.

## Resetting the walkthrough safely

Use **Results & audit → Safe reset** (checkbox + button). It runs
`delete_many({ note: "synthetic demo data" })` on the four demo collections
only — it never drops a database or collection and never touches records
without that marker. Then re-seed from the Ingest page.

## How cap enforcement works

```js
// one atomic conditional update — no read-then-write
updateOne(
  { accountId, capType: "local_tn",
    activeCount: { $lte: cap - requestedCount } },
  { $inc: { activeCount: requestedCount } }
)
// missing match ⇒ cap exceeded → reject, save nothing, audit
```

- The cap is **per account record** (unique `accountId`); accounts may have
  `parentAccount` / `superAccount` relationships, and a service package is
  attached by `accountId`.
- Which number states count toward the cap is one configurable business-rule
  function (`states_counting_toward_cap()` in `lib/cap_service.py`, currently
  `{"active"}`).
- Removing an eligible number frees capacity exactly once. Reactivation and
  transfer count as additions on the destination account.
- Lowering the cap below current usage keeps existing numbers and blocks new
  additions until usage falls below the cap.
- **Atomicity:** when the connected deployment supports multi-document
  transactions, reservation + inserts + audit run in one transaction. On a
  standalone deployment the demo falls back to reservation-first with
  compensation (refunds on failed inserts) — documented in the UI as a
  **non-atomic** fallback with the counter as the reconciliation anchor.
- **Accounts without a service package skip the capped path** — cap
  enforcement applies only to accounts carrying
  `serviceData.servicePackage` (alignment decision from the walkthrough).
- **Schema validation by account type:** an optional `$jsonSchema` validator
  for `accounts` (Schema & indexes page, apply behind a button) requires
  `accountId`/`name`/`accountType` on every account and forces SMB accounts
  (`accountType: "smb"`) to carry a complete service package
  (`packageId`, `capType`, numeric `cap` ≥ 1). Enterprise accounts may omit
  the package. Marked as a demo/design recommendation.

## Tests

Offline against an in-memory `mongomock` database — no cluster is contacted
and no real data is touched:

```bash
python -m pytest tests -v
```

Coverage: each ingestion route, duplicate prevention (validation + unique
index), exactly-at-cap success, over-cap rejection with no asset saved, the
99/100 concurrent race, CSV file-order/partial results, reactivation and
transfer counting, idempotent retry, cap lowered below usage, and
counter/asset consistency.

## Scope caveats

- The separate high-volume **robocall-mitigation workload (~1.8 billion
  records)** runs elsewhere and is intentionally absent from this demo's
  data model.
- Whether SMB traffic uses a **separate cluster/silo remains an open
  decision**; logical isolation in this demo database is a safety property
  of the walkthrough, not a production topology recommendation.
