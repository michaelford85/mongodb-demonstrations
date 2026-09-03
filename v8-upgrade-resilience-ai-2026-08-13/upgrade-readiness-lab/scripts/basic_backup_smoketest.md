# Backup / restore smoketest — manual flow

A deliberately manual checklist. The point of a pre-upgrade backup test is that
a human confirms the restore path works; automating it here would hide the step
that actually matters.

Run this **before** raising FCV or starting the upgrade. Record the timings — a
restore that takes four hours changes your maintenance window.

## Preconditions

- Continuous Cloud Backup or scheduled snapshots enabled on the source cluster.
- A restore target you are allowed to overwrite. Never restore a test into a
  production namespace.
- `MONGODB_URI` exported for the source cluster, and a second URI for the
  target when you get to the verification step.

## 1. Record the pre-backup state

```bash
python scripts/report_fcv_and_version.py
python scripts/report_index_and_feature_usage.py --db <your_database>
```

Save both outputs. They are the baseline you compare the restored cluster
against.

## 2. Confirm a usable snapshot exists

In the Atlas UI: **Cluster → Backup → Snapshots**.

| What to record | Why it matters |
|---|---|
| Most recent snapshot timestamp | Bounds your worst-case data loss |
| Snapshot retention policy | Confirms the snapshot survives the upgrade window |
| Oldest continuous restore point | Bounds how far back you can roll |
| Snapshot size | Rough predictor of restore duration |

If the newest snapshot predates your last schema or index change, take a manual
snapshot and wait for it to complete before continuing.

## 3. Restore to a separate target

Use **Restore → Restore to a different cluster** (or download the snapshot and
restore locally). Two rules:

- Restore to a **new or scratch** cluster, never to the source.
- Restore to the **same major version** as the source first. Testing a restore
  and a version jump at once tells you nothing about which one failed.

Record the wall-clock time from initiating the restore to the cluster becoming
available.

## 4. Verify the restored data

Point `MONGODB_URI` at the restored cluster and re-run both reports:

```bash
export MONGODB_URI="<restored-cluster-uri>"
python scripts/report_fcv_and_version.py
python scripts/report_index_and_feature_usage.py --db <your_database>
```

Compare against the step 1 baseline and confirm:

- [ ] Same databases and collections present.
- [ ] Document counts match, or differ only by writes after the snapshot point.
- [ ] Index count and index names match per collection — restores that silently
      drop an index are the classic post-restore performance surprise.
- [ ] Server version and FCV are what you expected.
- [ ] A representative read-heavy query from your workload returns the expected
      shape and row count.

## 5. Record the outcome

Paste into your upgrade notes:

```
backup smoketest
  date                  ...
  source version/FCV    ...
  snapshot timestamp    ...
  restore target        ...
  restore duration      ...
  count deltas          ...
  index deltas          ...
  verified by           ...
  result                pass / fail
```

## 6. Tear down

Delete the scratch restore target. A forgotten test cluster is both a cost and
a security exposure.

## If the test fails

Do not proceed with the upgrade. A failed restore before an upgrade is a
finding, not a blocker to work around — fix the backup configuration, take a
fresh snapshot, and re-run this flow from step 2.
