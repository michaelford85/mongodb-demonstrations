# Multi-Tenancy — Database-per-Tenant Isolation

This demo splits `sample_mflix.movies` across three tenant databases by release era, creates a scoped Atlas database user for each tenant, and runs live proof-of-isolation queries to show that tenants genuinely cannot see each other's data.

---

## What is the database-per-tenant pattern?

Each tenant gets their own database on a shared Atlas cluster. The cluster, hardware, backups, and operational overhead are shared — but every tenant's data lives in a separate namespace. A query against `classicflix.movies` has no visibility into `millenniumstream.movies`, even though both collections exist on the same cluster.

```
Atlas Cluster
├── classicflix/              ← Tenant A — movies before 1980
│   ├── movies
│   └── config
├── millenniumstream/         ← Tenant B — movies 1980–1999
│   ├── movies
│   └── config
└── modernplex/               ← Tenant C — movies 2000 and beyond
    ├── movies
    └── config
```

---

## Isolation patterns — choosing the right model

| Pattern | Isolation level | Tenant ceiling | Cost | Best for |
|---|---|---|---|---|
| **Database-per-tenant** *(this demo)* | Full namespace isolation | Hundreds–low thousands | Low (shared cluster) | SaaS with moderate tenant count, strong data separation requirement |
| **Collection-per-tenant** | Logical isolation via naming | Thousands | Low | High tenant count, simpler operational model, lower isolation requirement |
| **`tenant_id` field on shared collections** | Application-level only | Unlimited | Lowest | Very high tenant count, acceptable to rely on query filters for isolation |
| **Cluster-per-tenant** | Physical isolation | Unlimited (cost-bound) | High | Regulated industries, contractual data residency requirements |

**Database-per-tenant trade-offs worth knowing:**
- Each tenant can have its own indexes, schema validation rules, and collection structure without affecting any other tenant
- Atlas RBAC can restrict a database user to a single tenant's database — isolation is enforced at the server, not the application layer
- Atlas sharding can distribute tenant databases across shards as the platform grows
- Connection pool pressure increases with tenant count; very high tenant counts (10 000+) are better served by the `tenant_id` field pattern

---

## RBAC: a second line of defence

Namespace isolation prevents accidental cross-tenant reads when application routing is correct. RBAC prevents them even when it isn't.

`setup_tenants.py` creates one Atlas database user per tenant with roles scoped to that tenant's database only:

```json
{
  "username": "classicflix_app",
  "roles": [{ "databaseName": "classicflix", "roleName": "read" }]
}
```

A connection authenticated as `classicflix_app` physically cannot read `millenniumstream.movies`. Atlas returns an `OperationFailure` with an authorization error before any data is accessed — not an empty result set, a hard rejection. `demo.py` section 3 demonstrates this live.

> Atlas database users are **project-scoped**, not cluster-scoped. A user restricted to `classicflix` on one cluster is restricted on all clusters in the project.

---

## Files

| File | Purpose |
|---|---|
| `setup_tenants.py` | Splits `sample_mflix.movies` into three tenant databases and creates scoped Atlas database users. Run once. |
| `demo.py` | Runs the isolation demo (requires setup to have run). |
| `teardown_tenants.py` | Deletes the tenant databases and their Atlas database users. |
| `.env.example` | Environment variable template. |
| `requirements.txt` | Python dependencies. |

---

## Setup

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

```env
# Required for all scripts
MONGODB_URI=mongodb+srv://...

# Required for database user creation/deletion
ATLAS_PUBLIC_KEY=...
ATLAS_PRIVATE_KEY=...
ATLAS_PROJECT_ID=...

# Required for the RBAC section of demo.py
CLASSICFLIX_PASSWORD=...
MILLENNIUMSTREAM_PASSWORD=...
MODERNPLEX_PASSWORD=...
```

The Atlas API credentials are the same values used in `atlas-cluster-provisioning` and `online-archive`. The tenant passwords are the credentials `setup_tenants.py` will set when creating the Atlas database users — choose any strong passwords.

---

## Step 1 — Run setup

```bash
python3 setup_tenants.py
```

The script:
1. Reads all documents from `sample_mflix.movies`
2. Classifies each by year — handling malformed string values (e.g. `"1981è"`) by extracting the leading four-digit number and defaulting to `classicflix` if unparseable
3. Inserts each tenant's slice into its own database with a `config` document
4. Creates a scoped Atlas database user for each tenant via the Admin API

The script is idempotent — if the tenant databases already exist it reports their state and exits.

Expected output:

```
Classifying 23,530 movies from sample_mflix.movies...

  classicflix         3,845 movies  (year < 1980)
  millenniumstream    6,912 movies  (1980 – 1999)
  modernplex         12,773 movies  (year >= 2000)

Creating tenant databases...
  classicflix         3,845 movies + config  ✓
  millenniumstream    6,912 movies + config  ✓
  modernplex         12,773 movies + config  ✓

Creating Atlas database users...
  classicflix_app       created  (read → classicflix)
  millenniumstream_app  created  (read → millenniumstream)
  modernplex_app        created  (read → modernplex)
```

---

## Step 2 — Run the demo

```bash
python3 demo.py
```

The demo runs four sections:

### Section 1 — Namespace overview
Lists all three tenant databases, showing that each has a `movies` collection and a `config` collection. The same collection name exists in every tenant — the data is different, not the structure.

### Section 2 — Data isolation
The same `find_one` query is run against all three tenant databases using admin credentials — nothing prevents the reads. Each title exists in exactly one namespace because that is where the data lives, not because a filter excludes it. The explicit query string is printed before each result block so the audience can see exactly what is being executed.

| Title | Year | Expected tenant |
|---|---|---|
| Apocalypse Now | 1979 | `classicflix` |
| The Matrix | 1999 | `millenniumstream` |
| The Dark Knight | 2008 | `modernplex` |

### Section 3 — RBAC isolation
Uses `classicflix_app` for two back-to-back queries to contrast authorised and unauthorised access:

1. **Authorised read** — queries `classicflix.movies` successfully, confirming the credential works
2. **Cross-tenant attempt** — queries `modernplex.movies` with the same credential; Atlas raises `OperationFailure` before any data is accessed

The error message is printed in cleaned-up form (internal fields like `lsid` and `$clusterTime` are stripped) so the meaningful authorization message is clear.

> Requires `CLASSICFLIX_PASSWORD`, `MILLENNIUMSTREAM_PASSWORD`, and `MODERNPLEX_PASSWORD` to be set in `.env`. If any are missing this section is skipped with an explanation.

### Section 4 — Connection routing pattern
Shows how an application derives the correct database name from a tenant identifier (JWT claim, subdomain, API key lookup) and routes with `client[db_name]`.

### Section 5 — Two-layer isolation model
Prints a summary table distinguishing the two isolation layers and what each one does when a wrong-tenant read is attempted — a concrete takeaway for the audience.

---

## Teardown

```bash
python3 teardown_tenants.py
```

The script lists the databases and Atlas users that will be removed and asks for confirmation before proceeding. It accepts an optional env file argument, the same as `teardown_archive.py`:

```bash
python3 teardown_tenants.py path/to/other.env
```

`sample_mflix` is never modified by any script in this demo.

---

## Key talking points

- **Namespace isolation is structural** — data in `classicflix.movies` is invisible from `millenniumstream.movies` by definition, not by query filter. There is no application-level logic needed to enforce this.
- **RBAC is the second line of defence** — a scoped Atlas database user cannot read another tenant's database even if application routing logic has a bug. The authorization failure happens on the server before any data is touched.
- **Tenants are operationally independent** — each tenant database can have its own indexes, schema validation rules, and collection structure without affecting any other tenant.
- **The routing primitive is one line** — `client[db_name]`, where `db_name` is resolved from a JWT claim or subdomain. No tenant-awareness is needed in the query layer itself.
- **Malformed data is a real concern at scale** — a small number of `year` values in `sample_mflix` are stored as garbled strings rather than integers. The setup script handles this with a regex that extracts the leading four-digit year, defaulting to `classicflix` for anything unparseable. This is a good illustration of why input validation and schema enforcement matter.
- **This pattern scales to hundreds of tenants on a single cluster** — Atlas sharding can distribute tenant databases across shards as volume grows. For very high tenant counts (tens of thousands), the `tenant_id` field pattern on shared collections is more practical.

---

## MongoDB documentation

- [Multi-Tenancy Architecture Guide](https://www.mongodb.com/resources/products/capabilities/multi-tenancy)
- [Atlas Database Users](https://www.mongodb.com/docs/atlas/security-add-mongodb-users/)
- [Atlas Custom Database Roles](https://www.mongodb.com/docs/atlas/security-add-mongodb-roles/)
- [Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/)
- [Schema Validation (`$jsonSchema`)](https://www.mongodb.com/docs/manual/core/schema-validation/)
