# Upgrade Readiness Lab

A minimal, scriptable pre-flight check for moving a cluster from 7.x to 8.0.

**This is a generic pre-flight checklist, not a validation suite.** It is meant
to be read, adapted, and extended per environment. The checks are deliberately
shallow and cheap so they are safe to run against a live replica; every finding
is a prompt to investigate, not a verdict. No check here is a substitute for
reading the [8.0 compatibility notes](https://www.mongodb.com/docs/manual/release-notes/8.0-compatibility/)
for your own workload.

**Inspection and reporting only.** Nothing in this folder upgrades, provisions,
writes, or reconfigures anything. The cluster is assumed to exist already
(see `../../atlas-cluster-provisioning`). Connections come from `MONGODB_URI`.

## The checks

### `scripts/report_fcv_and_version.py`

Questions answered:

- What server version am I actually connected to?
- What is the feature compatibility version, and does it lag the binary version?
- Is this a replica set or a sharded cluster, and how many data-bearing nodes?

Why it matters: FCV must match the current major version before you start a
major upgrade, and 8.0 features stay dormant until FCV is raised afterwards. A
lagging FCV is the single most common reason an upgrade appears to do nothing.

The script detects whether you are pre-upgrade (7.x) or verifying post-upgrade
(8.x) and adjusts what it flags.

### `scripts/report_index_and_feature_usage.py`

Questions answered, per collection:

- How many indexes exist, and how close is the collection to the 64-index limit?
- Which indexes have seen zero use since the last process restart?
- Are there `2d` / `2dsphere` indexes, whose query input validation tightened
  in 8.0?
- Are there `text` indexes, TTL indexes, partial indexes, or hidden indexes?
- Are any documents storing `undefined`? 8.0 changed how `null` and `undefined`
  compare in `$eq`, `$in`, and `$lookup`, which can silently change results.
- Are index filters in use? They are deprecated in 8.0 in favour of query
  settings.
- Is stored server-side JavaScript present? `$where`, `$function`, and
  `$accumulator` are deprecated in 8.0.
- Are there `system.buckets.*` namespaces that are not time series collections?
  Those must be dropped or renamed before upgrading on 8.0.4 and earlier.

The `undefined` check samples documents rather than scanning, so it is
indicative. Treat a hit as a reason to run a full scan on that collection.

### `scripts/basic_backup_smoketest.md`

A manual backup and restore verification flow, with a paste-ready results block.
Deliberately not automated: the value of a pre-upgrade restore test is that a
human confirms the restore path and records how long it takes.

## Setup

```bash
cd upgrade-readiness-lab
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Then either export the URI directly:

```bash
export MONGODB_URI="mongodb+srv://user:password@your-cluster.mongodb.net/?retryWrites=true&w=majority"
```

or copy the example env file:

```bash
cp .env.example .env      # then paste your SRV string into MONGODB_URI
```

A read-only user is sufficient. Add `clusterMonitor` if you want `$indexStats`
access counts and the FCV to resolve rather than print `unavailable` — the
scripts degrade gracefully without it.

## Running

```bash
# Check 1 — version, FCV, topology
python scripts/report_fcv_and_version.py

# Check 2 — all non-system databases
python scripts/report_index_and_feature_usage.py

# Check 2 — specific databases, repeatable flag
python scripts/report_index_and_feature_usage.py --db orders --db customers

# Check 2 — widen the undefined-value sample
python scripts/report_index_and_feature_usage.py --db orders --sample-size 5000
```

Capture both reports for your notes:

```bash
python scripts/report_fcv_and_version.py | tee notes-fcv.txt
python scripts/report_index_and_feature_usage.py | tee notes-indexes.txt
```

Then work through `scripts/basic_backup_smoketest.md`.

## Expected output

Abridged; hostnames, counts, and versions vary by cluster.

```
==============================================================================
Check 1 — server version, FCV, and topology
==============================================================================

-- Server -------------------------------------------------------------------
  server version ............... 7.0.14
  feature compatibility ver .... 7.0
  storage engine ............... wiredTiger

-- Topology -----------------------------------------------------------------
  deployment type .............. replica set
  voting/data hosts ............ 3

-- Readiness ----------------------------------------------------------------
  [ note ] server is 7.0.14; target for this checklist is 8.0
  [ ok ]   FCV matches the server version; the usual precondition is met

-- Paste-ready line ---------------------------------------------------------
  server=7.0.14 fcv=7.0 type=replica set set=cluster0-shard-0 nodes=3

-- Summary ------------------------------------------------------------------
  [ ok ]   no follow-up items detected by this check
```

```
-- Database: orders ---------------------------------------------------------
  collections inspected ........ 2

  orders.orders
  estimated documents .......... 24
  index       keys            ops  flags
  ----------  --------------  ---  --------------------
  _id_        _id:1           118  -
  order_date  order_date:1    0    unused-since-restart
  [ ok ]   no undefined values in a 200 document sample

-- Summary ------------------------------------------------------------------
  [ warn ] orders.orders index order_date shows 0 accesses since the last
           process restart; confirm before carrying it into 8.0

  [ note ] 1 item(s) to review before upgrading
```

Both scripts end with the same `Summary` block, so output from different runs
and different clusters stays directly comparable.

## Adapting this per environment

- Add a check by dropping a new `report_*.py` into `scripts/` and importing the
  helpers from `_common.py` (`header`, `section`, `kv`, `ok`, `warn`, `note`,
  `table`, `footer`). Returning a list of finding strings and passing it to
  `footer()` keeps the output shape consistent.
- Tune `INDEX_WARN_THRESHOLD` and `SPECIAL_INDEX_TYPES` in
  `report_index_and_feature_usage.py` to match your standards.
- Set `DB_NAMES` in `.env` to scope every run to the namespaces you care about
  on a shared cluster.
- The `_indexStats` access counts reset on process restart, so a recently
  restarted node will over-report unused indexes. Check node uptime before
  acting on that finding.

## Live demo script

Copy-pasteable from a clean shell. Both scripts are read-only, so this is safe
to run against a live cluster as-is.

```bash
export MONGODB_URI='your-atlas-connection-string'

cd v8-upgrade-resilience-ai-2026-08-13/upgrade-readiness-lab

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# Check 1 — server version, FCV, topology
python scripts/report_fcv_and_version.py

# Check 2 — index inventory and 8.0 feature exposure, all non-system databases
python scripts/report_index_and_feature_usage.py

# Check 2, scoped to specific namespaces (--db is repeatable)
python scripts/report_index_and_feature_usage.py --db orders --db customers

# Check 2, with a wider sample for the undefined-value check
python scripts/report_index_and_feature_usage.py --db orders --sample-size 5000
```

To keep the output for your upgrade notes:

```bash
python scripts/report_fcv_and_version.py | tee notes-fcv.txt
python scripts/report_index_and_feature_usage.py | tee notes-indexes.txt
```

The third check is `scripts/basic_backup_smoketest.md` and has no script to run
— it is a manual backup and restore flow, walked through by hand. Do it before
raising FCV, not after, and record the restore timings.

Read both reports as prompts to investigate. A `[ warn ]` line means "confirm
this before upgrading", not "this will break".

## Optional checks

Depending on how deep you want to go with upgrade planning, you can add extra, environment-specific checks such as:

- A small backup and restore smoke test script or runbook that you execute against non-production data.
- A script that reports on a broader set of collections or databases (beyond the minimal examples here).
- Manual review steps for application-level behaviours that are hard to automate.

These are meant as add-ons for teams that want a more exhaustive checklist; they are not required to run the basic lab.

