# 01 — RPO / RTO

Observe what a failover looks like in real time on a live Atlas replica set.

## What this demonstrates

| Concept | How |
|---|---|
| **RPO = 0** | All writes use `w: "majority"`. A write is only acknowledged after a majority of replica-set members have it in their oplog, so a primary loss cannot lose data. |
| **RTO ≈ 10–20 s** | The watcher prints a new primary the moment the election completes. The writer pauses (PyMongo's retryable writes wait for a new primary) and resumes from the next sequence number — no gaps, no duplicates. |

The Atlas UI covers the configuration side (Continuous Backup, PIT slider). These two scripts cover the runtime side.

---

## Run it

Two terminals, side by side, both with the venv activated.

**Terminal A — writer**
```bash
python 01-rpo-rto/writer.py
```
You should see one line per insert at ~5/s.

**Terminal B — watcher**
```bash
python 01-rpo-rto/watcher.py
```
You should see one line on startup with the current primary, then nothing (it only prints on change or every 30 s as a heartbeat).

**Then trigger failover** in the Atlas UI:
1. Open the replica-set cluster.
2. Click **... → Test Primary Failover**.
3. Watch both terminals.

Expected:
- Watcher prints `CHANGE` with the new primary within 10–20 s.
- Writer pauses for a beat, then resumes with the next sequence number.
- No `FAILED` lines in the writer output.

---

## Clean up

```bash
mongosh "$REPLICASET_URI" --eval 'use architecture_demo; db.rpo_rto_events.drop()'
```
