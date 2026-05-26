# Pre-Session Checklist

Run through this checklist before the evaluation session. Items are grouped by when they need to happen — the **>24h before** block is the one that bites if skipped, because Atlas Online Archive runs on a daily schedule and the first run must complete before Topic 1 is demonstrable.

---

## >24 hours before the session

### Cluster

- [ ] Cluster provisioned via [`../atlas-cluster-provisioning`](../atlas-cluster-provisioning) with the Mumbai + Milan topology:
  ```env
  CLUSTER_CLOUD_PROVIDER=AWS
  CLUSTER_INSTANCE_SIZE=M30
  CLUSTER_NUM_REGIONS=2
  CLUSTER_REGIONS='[
    {"region_name":"AP_SOUTH_1","electable_nodes":3,"priority":7},
    {"region_name":"EU_SOUTH_1","electable_nodes":2,"priority":6}
  ]'
  ```
- [ ] Sample datasets loaded (Atlas UI → cluster → `...` → *Load Sample Dataset*) — `sample_mflix` is the one every demo uses
- [ ] `MONGODB_URI` connection string captured for reuse in each walkthrough's `.env`

### Online Archive (Topic 1) — must run a day ahead

- [ ] `cd ../mongodb-walkthrough/online-archive && cp .env.example .env` and fill in
- [ ] `pip install -r requirements.txt`
- [ ] `python3 setup_archive.py` — creates the index and archive rule
- [ ] Atlas UI → **Online Archive** shows the rule with status *Active*
- [ ] Allow the first archive job to run (daily schedule — typically completes within 24h of rule creation)

### Multi-Tenancy (Topic 3)

- [ ] `cd ../mongodb-walkthrough/multi-tenancy && cp .env.example .env` and fill in (including `CLASSICFLIX_PASSWORD`, `MILLENNIUMSTREAM_PASSWORD`, `MODERNPLEX_PASSWORD`)
- [ ] `pip install -r requirements.txt`
- [ ] `python3 setup_tenants.py` — splits `sample_mflix.movies` into three tenant databases and creates scoped Atlas users
- [ ] Atlas UI → **Database Access** shows `classicflix_app`, `millenniumstream_app`, `modernplex_app` with per-database `read` roles

### Connection Pooling (Topic 2)

- [ ] `cd ../mongodb-walkthrough/connection-pooling && cp .env.example .env` and fill in
- [ ] `pip install -r requirements.txt`

### Multi-Region (Topic 4 — optional script demo)

- [ ] `cd ../mongodb-walkthrough/multi-region && cp .env.example .env` and fill in
- [ ] `pip install -r requirements.txt`

---

## Morning of the session

### Verify Online Archive ran

- [ ] Atlas UI → **Online Archive** → rule card shows non-zero **Last Archive Run** and **Total Data Archived**
- [ ] Atlas UI → **Online Archive** → **Connect** → copy the federated `mongodb://...` URI
- [ ] Add it as `FEDERATED_URI` in `../mongodb-walkthrough/online-archive/.env`
- [ ] `cd ../mongodb-walkthrough/online-archive && python3 query_demo.py` runs cleanly and shows the hot vs. federated timing gap
- [ ] `python3 title_lookup.py "The Matrix"` returns `cold (archived)` and `python3 title_lookup.py "Curious George"` returns `hot (live)`

### Dry-run every script once

- [ ] `cd ../mongodb-walkthrough/multi-tenancy && python3 demo.py` completes all four sections without error
- [ ] `cd ../mongodb-walkthrough/connection-pooling && python3 demo.py` prints the three-row timing table
- [ ] (Optional) `cd ../mongodb-walkthrough/multi-region && python3 read_preference_demo.py` shows `nearest` routing to a Milan secondary

### Atlas UI tabs to pre-open (in this order, one tab each)

1. **Cluster overview** — for Topic 4 region map
2. **Online Archive** — for Topic 1 rule card + Connect dialog
3. **Database Access** — for Topic 3 scoped users
4. **Network Access** → **Peering** tab — for Topic 4 peering walkthrough
5. **Network Access** → **Private Endpoint** tab — for Topic 4 alternative-network mention
6. **Real-time performance** — for Topic 4 failover narration

### Terminals to pre-stage

| Terminal | Working directory | Purpose |
|---|---|---|
| 1 | `mongodb-walkthrough/online-archive` | `query_demo.py`, `title_lookup.py` |
| 2 | `mongodb-walkthrough/connection-pooling` | `demo.py` |
| 3 | `mongodb-walkthrough/multi-tenancy` | `demo.py` |
| 4 | `mongodb-walkthrough/multi-region` | optional read-preference demo |

Each terminal: confirm `.env` is loaded and `python3 -c "import pymongo; print(pymongo.__version__)"` works.

---

## Final 10 minutes

- [ ] Network: tether available in case venue Wi-Fi blocks `mongodb+srv` SRV lookups
- [ ] Atlas UI logged in and **not** about to expire the session
- [ ] Browser zoom set high enough for the room
- [ ] Side-by-side schema view from [`../mongodb-walkthrough/data-modeling/README.md`](../mongodb-walkthrough/data-modeling/README.md) open in a tab — needed for the Topic 5 talk-through
- [ ] Cluster `...` menu confirmed available for the **Test Failover** moment in Topic 4 (the option is greyed out for ~5 minutes after a recent failover — don't run it ad-hoc just before the call)

---

## If something is broken at start of session

| Symptom | Quick recovery |
|---|---|
| Federated URI returns auth error | Re-copy from Atlas UI → **Online Archive** → **Connect**; the host can rotate after rule edits |
| `setup_tenants.py` already created users — passwords forgotten | Re-run `setup_tenants.py`; it is idempotent for the data and re-applies the passwords from `.env` to the existing users |
| Archive shows 0 documents archived | The first daily job hasn't run yet — fall back to Atlas UI walkthrough of the rule definition and partition fields; defer the timed query demo |
| Topic 3 RBAC section skipped | One of the `*_PASSWORD` env vars is empty — set it and re-run `demo.py` |
| Multi-region demo writes are slow | Expected — `w="majority"` is cross-region by design; lead with this in the narrative rather than apologising for it |
