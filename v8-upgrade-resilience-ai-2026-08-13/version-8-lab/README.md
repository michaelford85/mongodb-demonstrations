# Version 8 Lab

A self-contained sampler that runs the **same task twice** against a MongoDB 8.0+
Atlas cluster: once the way you would write it on 7.x, once using a Version 8
feature. Each demo prints both forms plus a short DIFF block so the change in
behaviour or complexity is visible in the terminal.

The cluster is assumed to exist already (see `../../atlas-cluster-provisioning`).
Nothing in this lab provisions, scales, or deletes a cluster, and every
connection comes from `MONGODB_URI`.

## The two features

### 1. `$toUUID` — server-side string to `BinData` subtype 4

Applications that inherit UUIDs as strings (relational migration, JSON API)
usually store them as strings, then convert client-side whenever they need the
compact binary form.

| | 7.x pattern | 8.x pattern |
|---|---|---|
| Where the conversion happens | application code, per document | inside the aggregation pipeline |
| Code you maintain | `Binary(uuid.UUID(s).bytes, UUID_SUBTYPE)` per field | `{"$toUUID": "$order_id"}` |
| Usable in `$match` / `$group` / `$merge` | no, only after the round trip | yes, in the same pipeline |

`$toUUID` is shorthand for the long form, which also works in 8.0:

```js
{ $convert: { input: "$order_id", to: { type: "binData", subtype: 4 }, format: "uuid" } }
```

### 2. Query settings — guardrails on a query shape, with no application deploy

The demo picks a deliberately bad shape: an unindexed regex scan over
`orders.note`. It is cheap on 24 documents and ruinous at production scale.

| | 7.x pattern | 8.x pattern |
|---|---|---|
| Lever | change the application, or `planCacheSetFilter` | `setQuerySettings` |
| Scope | a single `mongod` | cluster-wide |
| Survives restart | no | yes |
| Application change | required | none |
| Targeting | collection + index | `queryShapeHash` |
| Status in 8.0 | index filters deprecated | recommended replacement |

Two settings are demonstrated against the same shape:

* `reject: true` — the server refuses the query outright (`QueryRejectedBySettings`).
* `indexHints` — the planner may only consider the listed indexes for that shape.

Registered settings are read back with the `$querySettings` aggregation stage.

`setQuerySettings` merges into whatever is already registered for a query shape,
it does not replace it. The demo therefore removes the `reject` before applying
`indexHints`; otherwise both apply to the same `queryShapeHash` and the query is
still refused. Because no index covers `note`, the pinned shape falls back to a
collection scan rather than using `order_date_1`.

## Layout

```
version-8-lab/
├── data/
│   ├── customers.json      8 synthetic tenants, string UUID ids
│   └── orders.json         24 synthetic orders, string UUID ids
├── app/
│   ├── config.py           .env driven connection + namespace
│   ├── seed.py             load the data, create the demo index
│   ├── demo_uuid.py        feature 1
│   ├── demo_settings.py    feature 2
│   ├── render.py           terminal formatting helpers
│   └── main.py             CLI entry point
├── .env.example
└── requirements.txt
```

## Setup

```bash
cd version-8-lab
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then paste your SRV string into MONGODB_URI
```

The database user needs `readWrite` on the lab database, plus `atlasAdmin` (or
the `querySettings` privileges) to run `setQuerySettings` and
`removeQuerySettings` against `admin`.

## Running

```bash
python app/main.py seed            # load data + create the order_date index
python app/main.py seed --drop      # reload from scratch
python app/main.py uuid             # feature 1
python app/main.py settings         # feature 2
python app/main.py all --drop       # reload, then run both demos
python app/main.py clean            # remove query settings and drop the database
```

`settings` removes its own query settings when it finishes. Add
`--keep-settings` to leave them registered so you can inspect them in mongosh,
then tidy up with `python app/main.py clean`.

The CLI checks `buildInfo` first and exits with a clear message if the cluster
reports anything below 8.0.

## Expected output

Abridged — hashes, plan names, and ids vary by cluster.

```
Connected to MongoDB 8.0.x, database version_8_lab
Inserted 24 orders and 8 customers into version_8_lab
Created index order_date_1 on orders.order_date

==============================================================================
Feature 1 — $toUUID: string UUIDs to BinData subtype 4
==============================================================================

-- BEFORE (7.x style) — server returns strings, app converts ----------------
  ... pipeline ...
  plus, for every document returned:
      Binary(uuid.UUID(doc["order_id"]).bytes, UUID_SUBTYPE)
  order_id                                     customer_id  plan
  UUID('8b2e4d10-0000-4c3a-9f11-000000000001') UUID('3f1c...') free

-- AFTER (8.x) — $toUUID converts server-side -------------------------------
  ... same pipeline, with {"$toUUID": "$order_id"} in $project ...

-- DIFF ---------------------------------------------------------------------
  same result documents .............. True
  client-side conversion code ........ 2 lines per document -> 0

==============================================================================
Feature 2 — query settings: block or pin a query shape
==============================================================================

-- BEFORE (7.x style) — the shape runs, and keeps running -------------------
  plan .......... COLLSCAN
  docs examined . 24  (returned 6)
  query ran, returned 6 documents

-- AFTER (8.x) — reject the shape with setQuerySettings ---------------------
  query refused by the server: QueryRejectedBySettings (code 411)
    Query rejected by admin query settings

-- AFTER (8.x) — or pin the shape to an index instead -----------------------
  plan .......... COLLSCAN
  docs examined . 24  (returned 6)
  query ran, returned 6 documents

-- Settings currently registered on the cluster -----------------------------
  queryShapeHash .. F643...
  settings ........ {'indexHints': [...], 'comment': '...'}
```

## Reusing this for another workshop

* Swap `data/*.json` for your own documents; `seed.py` parses any `order_date`
  or `signup_date` field into a BSON date and inserts the rest verbatim.
* Change `DB_NAME` and the collection names in `.env` to isolate parallel runs
  on a shared cluster.
* To demonstrate a different feature, add `app/demo_<name>.py` exposing `run()`
  and register it in the `choices` list in `app/main.py`.

## Live demo script

Copy-pasteable from a clean shell. `MONGODB_URI` is read from the environment,
so exporting it works whether or not you have created a `.env`.

```bash
export MONGODB_URI='your-atlas-connection-string'

cd v8-upgrade-resilience-ai-2026-08-13/version-8-lab

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# Load the seed data and create the order_date index
python app/main.py seed --drop

# Feature 1 — prints BEFORE (7.x style), AFTER (8.x), and a DIFF block
python app/main.py uuid

# Feature 2 — same three blocks for query settings
python app/main.py settings

# Tidy up afterwards: remove query settings, drop the lab database
python app/main.py clean
```

There is no separate "before" script and "after" script. Each demo command runs
both forms of the same task back to back in one process and prints them
together, which is the point — the comparison is only convincing when the two
results sit next to each other on screen.

To run the whole thing as one uninterrupted sequence:

```bash
python app/main.py all --drop
```

Add `--keep-settings` to the `settings` or `all` command to leave the query
settings registered so you can inspect them in mongosh before running `clean`.

## Optional variations

If you have more time with your team, you can extend this lab by:

- Adding one or two additional Version 8 features on the same dataset (for example, another aggregation or query pattern that improves on a 7.x approach).
- Capturing and comparing query plans (before vs after) for the demo queries and pasting them into slides or notes.
- Duplicating the lab against a different synthetic schema to discuss trade-offs for another workload.

These variations are intentionally optional and are not required for the core live demo.

