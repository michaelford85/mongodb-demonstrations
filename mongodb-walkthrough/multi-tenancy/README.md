# Multi-Tenancy — Database-per-Tenant Isolation

This demo shows the **database-per-tenant** pattern: each tenant gets their own database on a shared Atlas cluster, providing full namespace isolation without requiring separate clusters.

---

## The pattern

```
Atlas Cluster
├── tenant_a/           ← Tenant A's database
│   ├── orders
│   ├── catalog
│   └── config
├── tenant_b/           ← Tenant B's database
│   ├── orders
│   ├── catalog
│   └── config
└── tenant_c/ ...
```

All tenants share the same cluster (and therefore the same hardware, backups, and operational overhead), but their data never occupies the same namespace. A query against `tenant_a.orders` has no visibility into `tenant_b.orders`.

---

## What the demo shows

1. **Namespace structure** — lists both tenant databases and their collections
2. **Tenant A query** — reads from `sample_mflix.movies` (existing sample data)
3. **Tenant B query** — reads from a freshly created lightweight database
4. **Isolation check** — demonstrates that Tenant B's database has no `movies` collection; Tenant A's data cannot be reached from Tenant B's namespace
5. **Connection pattern** — shows how the application selects the right database per request

Tenant B's database is created at the start of the script and dropped at the end. `sample_mflix` is never modified.

---

## Setup

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
# Fill in MONGODB_URI
```

## Run

```bash
python3 demo.py
```

---

## Key talking points

- The application determines the database name from the tenant context (e.g. a field in a JWT, a subdomain, an API key lookup) and calls `client[db_name]` — one line of routing logic
- Tenants can have different schemas, indexes, and collection structures within their database without affecting other tenants
- Atlas RBAC can grant a database user access to a single tenant's database only, providing an additional security layer
- This pattern scales to hundreds or thousands of tenants on a single cluster; Atlas sharding can distribute tenant databases across shards if needed
- Alternative patterns (collection-per-tenant with a `tenant_id` field, or full cluster-per-tenant) trade off isolation granularity against operational simplicity and cost
