# Atlas → ServiceNow CMDB Synchronization Demo

An exploratory, "art of the possible" demonstration of synchronizing a **read-only MongoDB Atlas inventory into a ServiceNow CMDB** through the documented **Identification and Reconciliation (IRE) API** — without writing directly to CMDB tables and without bypassing identification and reconciliation.

> **This is a demonstration, not a production connector.** It is not an officially supported MongoDB–ServiceNow integration (no such official connector is claimed or known to exist). Everything here is customer-neutral synthetic example data. Treat it as a reference architecture to adapt, validate, and harden before any real use.
>
> **Reading this as a customer example?** The intended takeaway is the *pattern*: a read-only, least-privilege Atlas inventory feed normalized into a CMDB-ready hierarchy (org → project → cluster → cluster nodes), ingested through ServiceNow's IRE API so identification and reconciliation — not hand-written table inserts — decide what gets created or updated. The specific CI classes, fields, and identification rules must be designed for your own CMDB class model and tested on a **non-production instance** first. See [Tested walkthrough](#tested-walkthrough-end-to-end-on-a-developer-instance) for the exact path that was run and verified, and [Limitations](#limitations-and-known-gaps) for what this demo does *not* solve.

---

## What it demonstrates

1. **Read-only discovery** of an Atlas organization → projects → clusters → cluster processes (hosts) using the Atlas Administration API v2.
2. **Normalization** of those resources into a CMDB-ready model with stable source identifiers, explicit parent/child relationships, and a small, verified set of inventory attributes.
3. **A ServiceNow ingestion boundary** using the IRE API (`POST /api/now/identifyreconcile`), the currently documented inbound REST pattern that feeds the Identification and Reconciliation engine. Nothing is written directly to `cmdb_ci_*` tables.
4. **A mock/demo mode** that runs end-to-end with bundled synthetic fixtures and **zero credentials**, showing the normalized inventory and the exact IRE payload that would be sent.
5. **Safe-by-default behavior**: dry-run is the default; live writes require both `--apply` **and** `SERVICENOW_ALLOW_WRITES=true`.

## Architecture and data flow

```
            read-only                       normalize + map                ingest (IRE)
┌──────────────────────┐        ┌────────────────────────────┐        ┌──────────────────────────┐
│ Atlas Administration │        │ normalizer.py              │        │ servicenow_client.py     │
│ API v2 (cloud.       │        │  org/project/cluster/      │        │  POST /api/now/          │
│  mongodb.com)        │───────▶│  process → CIRecord        │───────▶│   identifyreconcile      │
│                      │        │  mapping.json → CI class,  │        │  (+ /query simulation)   │
│  atlas_client.py     │        │  attributes, relations     │        │                          │
└──────────────────────┘        └────────────────────────────┘        └──────────────────────────┘
        or
┌──────────────────────┐               │                                     │
│ mock_atlas.py        │               ├── ire_payload.py                   ├── IRE identifies CIs
│ (fixtures/           │───────────────┤   items[] + relations[]            │   (dedupe rules)
│  inventory.json)     │               └── output/*.json artifacts          └── reconciles attrs
└──────────────────────┘                (dry-run writes these instead)           (source precedence)
```

The three stages are deliberately separable:

| Stage | Module | Needs credentials? |
|---|---|---|
| Inventory retrieval | `atlas_client.py` (live) or `mock_atlas.py` (fixtures) | live only, read-only |
| Normalization + mapping | `normalizer.py`, `config.py`, `mapping.json` | never |
| ServiceNow transport | `servicenow_client.py` + `ire_payload.py` | only for `--validate` / `--apply` |

### Discovery endpoints used (verified against the v2 API spec)

| Atlas endpoint | Purpose | Required role (spec) |
|---|---|---|
| `GET /api/atlas/v2/orgs/{orgId}` | Organization name | Organization Member |
| `GET /api/atlas/v2/orgs/{orgId}/groups` | All projects in the org | Organization Member |
| `GET /api/atlas/v2/groups/{groupId}/clusters` | Clusters per project | Project Read Only |
| `GET /api/atlas/v2/groups/{groupId}/processes` | Cluster processes / hosts | Project Read Only |

Pagination uses `pageNum` / `itemsPerPage` (max 500) / `includeCount` on every call. Authentication uses a **service account** (OAuth 2.0 client credentials against `POST /api/oauth/token`, 1-hour Bearer tokens — MongoDB's recommended method). Legacy API-key HTTP Digest is supported as a fallback (`ATLAS_AUTH=api_key`) but discouraged by MongoDB docs.

## Quick start (mock mode, no credentials)

```bash
cd atlas-servicenow-cmdb-demo
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python run_demo.py                 # dry-run on synthetic fixtures
```

Output: a per-record listing of the normalized inventory, the relationship list, and two artifacts under `output/`:

- `output/normalized_inventory.json` — every discovered resource with source IDs, parent links, and normalized attributes.
- `output/ire_payload.json` — the exact JSON that would be POSTed to the ServiceNow IRE API.

Useful flags:

```bash
python run_demo.py --limit 1       # only the first project
python run_demo.py --quiet         # counts only, still writes artifacts
python run_demo.py --source mock   # explicit (default)
```

## Tests

```bash
python -m pytest tests -q
```

Covers: mock inventory retrieval and fixture/API-schema conformance, Atlas client pagination and 429 retry/backoff (fake transport, no network), normalization and relationship mapping (including the process→cluster heuristic and orphan fallback), IRE payload structure, and the dry-run safeguards (no ServiceNow call by default; `--apply` refused without the env opt-in).

## Optional: live Atlas discovery (read-only)

1. Create an **organization service account** in Atlas (Organization Access Manager → Service Accounts) with the least-privilege roles: **Organization Member** + **All Projects Read Only**. Both endpoints above work with these roles per the API spec; nothing in this demo requires a write role.
2. Copy `.env.example` to `.env` and set `DEMO_SOURCE=atlas`, `ATLAS_ORG_ID`, `ATLAS_CLIENT_ID`, `ATLAS_CLIENT_SECRET`.
3. If your org enforces an API access list, add the runner's egress IP for the service account.
4. Run `python run_demo.py --source atlas` (still dry-run — nothing is sent to ServiceNow).

## Optional: ServiceNow ingestion

Two non-destructive and one destructive mode:

| Mode | Command | What it does |
|---|---|---|
| Dry-run (default) | `python run_demo.py` | Builds the payload, writes artifacts, contacts no one. |
| Validate | `python run_demo.py --validate` | POSTs to the **IRE simulation endpoint** `/api/now/identifyreconcile/query` — runs identification/reconciliation logic **without committing** to the database. Requires ServiceNow credentials. |
| Apply | `python run_demo.py --apply` | POSTs to `/api/now/identifyreconcile` for real. Requires **both** the flag **and** `SERVICENOW_ALLOW_WRITES=true`. |

### ServiceNow prerequisites

- **Instance + user**: a user with the `itil` or `asset` role (the IRE API's documented requirement). Use a dedicated integration user.
- **Discovery source**: the `sysparm_data_source` query parameter must match a **choice value of the `discovery_source` field on `cmdb_ci`**. Create a custom discovery source record (for example *Atlas*) in your instance first, and set `SERVICENOW_DISCOVERY_SOURCE` / `discovery_source` in `mapping.json` to that exact value.
- **CI classes and fields**: every class and field name in `mapping.json` must exist in your instance. The defaults are a *proposal* — validate them (or replace them with your own classes, e.g. a custom `cmdb_ci_atlas_cluster`) before applying. Verified findings from testing against a stock developer instance:
  - Stock instances ship the OOB `Database [cmdb_ci_database]` and `Cloud Database [cmdb_ci_cloud_database]` identification rules as *dependent* rules with hard-coded relation expectations (a database must contain cloud-database children; a cloud database must be hosted on a logical datacenter). The IRE rejects payloads that don't satisfy them (`MISSING_DEPENDENCY`), requires *some* active rule per class (`IDENTIFICATION_RULE_MISSING` if you deactivate them), and rule edits made directly via the table API don't refresh the IRE rule cache — so reusing OOB database classes without also modeling their expected dependents does not work.
  - `mapping.pdi.json` is included for exactly this case: it maps every resource to `cmdb_ci_service`, which identifies by name with no dependencies, and it validates and applies cleanly on a stock developer instance (used for the live end-to-end test).
  - The production answer is **custom CI classes with identification rules authored in the rule editor UI** (the editor flushes the rule cache), not repurposed OOB classes.
  - Items are always attributed with `sys_object_source_info`, so re-runs reconcile through `sys_object_source` matching (observed: second `--apply` returned `NO_CHANGE` for every item, zero duplicates) even for classes without name-based identification rules.
- **Identification rules**: the IRE identifies CIs using your configured identifier entries; configure them for the classes in use so re-runs update rather than duplicate.
- **Relationship types**: `relations[].type` must be a `name` value from your `cmdb_rel_type` table (default used here: `Contains::Contained by`).
- **IntegrationHub ETL**: if you prefer Import Sets/ETL spokes over calling the IRE REST API directly, the same `output/ire_payload.json` items map cleanly onto an ETL/Import Set design; the IRE remains the identification and reconciliation boundary either way. See the IntegrationHub ETL docs linked below.

### Risks of `--apply` (read before enabling)

- It creates/updates CIs and relationships in a real CMDB via IRE — intended for a **sandbox/dev instance first**.
- Wrong class/field/relationship names or missing identification rules can produce duplicates or failed identification (payloads landing in incomplete-payload handling).
- `SERVICENOW_ALLOW_WRITES` is a deliberate two-key switch (flag + env) so a stray command or a copied `.env` cannot silently write.

## Tested walkthrough: end-to-end on a developer instance

This is the exact sequence that was run and verified against a stock ServiceNow **developer (PDI) instance** and a live read-only Atlas organization: one org, one project, one replica-set cluster, three cluster nodes → 6 CIs, 5 relationships inserted on the first `--apply`, and every item `NO_CHANGE` (no duplicates) on a second `--apply`. You can reproduce it against your own developer instance. All commands are REST/curl — no GUI needed except where noted.

**0. Prerequisites** — the demo checked out with its venv (`pip install -r requirements.txt`), a `.env` with the Atlas block (`DEMO_SOURCE=atlas`, `ATLAS_ORG_ID`, service-account credentials) and the ServiceNow block (`SERVICENOW_INSTANCE_URL`, `SERVICENOW_USERNAME`, `SERVICENOW_PASSWORD`), and `SERVICENOW_ALLOW_WRITES=false` until the final step. If Atlas returns **403 "access list of ip ranges"**, add your egress IP (`curl -s ifconfig.me`) to the service account's API access list in the Atlas UI.

**1. Register a discovery source** (required — the IRE API silently parks payloads from unregistered sources):

```bash
curl -s -X POST "https://<instance>.service-now.com/api/now/table/sys_choice" \
  -u '<user>:<password>' -H "Content-Type: application/json" \
  -d '{"name":"cmdb_ci","element":"discovery_source","label":"Atlas","value":"atlas"}'
```

Shell gotcha: single-quote the `-u` argument — passwords containing `$` are corrupted inside double quotes. If you get `User is not authenticated` with correct credentials, the instance was likely waking from hibernation; retry.

**2. Check which CI classes exist on your instance** (200 = present, 400/404 = missing):

```bash
for c in cmdb_ci_service cmdb_ci_database cmdb_ci_cloud_database; do
  curl -s -o /dev/null -w "$c -> %{http_code}\n" -u '<user>:<password>' \
    "https://<instance>.service-now.com/api/now/table/$c?sysparm_limit=1"
done
```

**3. Pick the mapping file.** On a stock developer instance the OOB database classes exist but their identification rules are dependent-class rules that reject a self-contained hierarchy (details under *ServiceNow prerequisites* above). Use the included **`mapping.pdi.json`** (all resources → `cmdb_ci_service`, which identifies by name with no dependencies) by setting `DEMO_MAPPING_FILE=mapping.pdi.json` in `.env`. On a real deployment you would instead define custom classes and identification rules in the rule editor.

**4. Simulate first — nothing commits:**

```bash
python run_demo.py --validate
```

Every item should return `operation: INSERT` with `errorCount: 0`. If items show `MISSING_DEPENDENCY` or `IDENTIFICATION_RULE_MISSING`, the chosen classes' identification rules don't accept this hierarchy — switch mapping or adjust rules; don't proceed to `--apply` with errored items.

**5. Apply for real** (set `SERVICENOW_ALLOW_WRITES=true` in `.env` first):

```bash
python run_demo.py --apply
```

**6. Verify the results over REST:**

```bash
# the CIs, attributed to the Atlas discovery source (expect one per record in the run summary)
curl -s -u '<user>:<password>' -G \
  "https://<instance>.service-now.com/api/now/table/cmdb_ci_service" \
  --data-urlencode "sysparm_query=discovery_source=atlas" \
  --data-urlencode "sysparm_fields=sys_id,name,short_description,discovery_source" \
  --data-urlencode "sysparm_display_value=true"

# the relationships (expect the Contains chain: org→project, project→cluster, cluster→each node)
curl -s -u '<user>:<password>' -G \
  "https://<instance>.service-now.com/api/now/table/cmdb_rel_ci" \
  --data-urlencode "sysparm_query=child.nameSTARTSWITH<your-cluster-name>" \
  --data-urlencode "sysparm_fields=parent.name,child.name,type" \
  --data-urlencode "sysparm_display_value=true"

# source-key tracking that makes re-runs reconcile (expect one record per CI)
curl -s -u '<user>:<password>' -G \
  "https://<instance>.service-now.com/api/now/table/sys_object_source" \
  --data-urlencode "sysparm_query=source_name=atlas" \
  --data-urlencode "sysparm_fields=source_name,source_native_key"
```

**7. Prove reconciliation** — run `python run_demo.py --apply` a second time. Every item should return `operation: NO_CHANGE` with `sys_object_source MATCHED`, and the CI count from step 6 should be unchanged. That's identification and reconciliation doing their job: same Atlas resources → same CIs, updated rather than duplicated.

**What this walkthrough deliberately does not cover** (and would be required before any production use): a durable sync schedule, deletion/staleness handling when Atlas resources disappear, custom CI classes and identification rules, OAuth instead of basic auth, batching for large inventories, and testing against anything other than a disposable developer instance.

## Proposed CI mapping (configurable via `mapping.json`)

| Atlas resource | Proposed ServiceNow class | Parent | Relationship |
|---|---|---|---|
| Organization | `cmdb_ci_cloud_service` | — | — |
| Project | `cmdb_ci_cloud_service_container` | organization | `Contains::Contained by` |
| Cluster | `cmdb_ci_database` | project | `Contains::Contained by` |
| Process (`mongod`/`mongos`) | `cmdb_ci_database_instance` | cluster (heuristic), else project | `Contains::Contained by` |

Notes on the model:

- **Atlas is a managed cloud database service.** Its cluster processes run on MongoDB-managed infrastructure that the customer does not manage, so processes are *not* modeled as customer-managed servers/VMs (`cmdb_ci_linux_server` etc.). A database-instance-style class (or a custom subclass) is the proposed fit; judge this against your own CMDB class model.
- **`cmdb_ci_database_instance` may not exist in every instance** — the class layout varies by version and installed plugins. The mapping file exists precisely so you can point resources at classes that do exist (including custom ones) without code changes.
- Attributes pushed per class are limited to the `attributes` map in `mapping.json` (`name`, `version`, `short_description` by default). The normalizer collects more verified attributes (connection string, provider/region/size, state, replica set, shard, last ping, ...) — visible in `output/normalized_inventory.json` — but they are only sent once you map them to real fields on the target class.

### Normalized inventory attributes (verified against the v2 API response schemas)

| Resource | Fields (source of truth) |
|---|---|
| Organization | `id`, `name` |
| Project (Group) | `id`, `name`, `orgId`, `created`, `clusterCount` |
| Cluster | `id`, `groupId`, `name`, `clusterType`, `mongoDBVersion`, `mongoDBMajorVersion`, `stateName`, `createDate`, `paused`, `backupEnabled`, `connectionStrings.standardSrv`, `replicationSpecs[].regionConfigs[].{providerName, regionName, electableSpecs.instanceSize}` |
| Process (ApiHostView) | `id` (hostname:port), `groupId`, `hostname`, `port`, `userAlias`, `typeName` (`REPLICA_PRIMARY`, `REPLICA_SECONDARY`, `SHARD_MONGOS`, `SHARD_CONFIG`, `SHARD_PRIMARY`, `SHARD_SECONDARY`, `RECOVERING`, `SHARD_STANDALONE`, `NO_DATA`), `replicaSetName`, `shardName`, `version`, `created`, `lastPing` |

No field outside these verified response schemas is used.

## Stability and identification assumptions

- **Stable source identifiers**: organization, project, and cluster records use the Atlas 24-hex resource IDs as `source_native_key` (stable for the resource's lifetime). The IRE `sys_object_source_info` block carries `source_feed`, `source_name` (discovery source), `source_native_key`, and `source_recency_timestamp` so reconciliation can order sources by recency.
- **Process identifiers are NOT guaranteed stable.** Atlas's process ID is `hostname:port`; Atlas replaces hosts during maintenance/scaling, and the API does not expose a durable per-process GUID. Repeated syncs may therefore create new process CIs after host replacement unless you add identification rules keyed on something more stable (e.g. cluster + shard + replica-set role), or treat process CIs as transient. This is an explicit gap, not a solved problem.
- **Host IPs are never assumed stable** and are not collected at all; only hostnames as returned by the API are used.
- **Process → cluster linkage is heuristic.** The processes endpoint does not return a cluster ID; the demo matches the process hostname's first DNS label against cluster names (cluster names are unique within a project). Unmatched processes fall back to the project CI (the fixtures include one such orphan to demonstrate this path).

## Limitations and known gaps

- **Read-only, point-in-time inventory.** No change detection, no continuous sync, no deletion/staleness handling — a real integration needs a schedule plus CMDB retirement logic for resources that disappear from Atlas.
- **Coverage**: Flex (`/flexClusters`) and serverless (`/serverlessClusters`) deployments live on separate endpoints and are not discovered; only `clusters`-endpoint deployments are. Other CMDB-relevant resources (network peering, private endpoints, backup policies) are out of scope.
- **Class/field validation is manual.** The demo validates payload *structure*, not that your instance accepts the chosen classes/fields; use `--validate` (IRE simulation) against a sandbox instance for that.
- **No ServiceNow OAuth**: basic auth for the integration user only (fine for a demo; use OAuth/OIDC in real deployments if your instance policy requires it).
- **No pagination on the ServiceNow side** (single POST); very large inventories may need batching.
- **Not supported**: this is not an official MongoDB–ServiceNow connector, has no support entitlement, and has not been tested against a production ServiceNow instance.

## Authoritative documentation used

- [Atlas Administration API overview](https://www.mongodb.com/docs/atlas/api/atlas-admin-api/)
- [Atlas Administration API authentication](https://www.mongodb.com/docs/atlas/api/api-authentication/) (service accounts / OAuth 2.0; API keys = legacy digest)
- [Generate service account token](https://www.mongodb.com/docs/atlas/api/service-accounts/generate-oauth2-token/)
- [Atlas Administration API v2 specification](https://www.mongodb.com/docs/api/doc/atlas-admin-api-v2/) (endpoints, pagination parameters, response schemas, per-endpoint role requirements; also mirrored in the [atlas-sdk-go OpenAPI spec](https://github.com/mongodb/atlas-sdk-go/tree/main/openapi))
- [ServiceNow Identification and Reconciliation API (Yokohama API reference)](https://www.servicenow.com/docs/bundle/yokohama-api-reference/page/integrate/inbound-rest/concept/c_IdentifyReconcileAPI.html)
- [ServiceNow IntegrationHub ETL (Washington DC)](https://www.servicenow.com/docs/bundle/washingtondc-servicenow-platform/page/product/configuration-management/concept/integrationhub-etl.html)

## Repository conventions

As with every demo in this repository: `.env` is git-ignored, `.env.example` holds placeholders only, no secret is ever accepted as a command-line argument, and the folder is self-contained.
