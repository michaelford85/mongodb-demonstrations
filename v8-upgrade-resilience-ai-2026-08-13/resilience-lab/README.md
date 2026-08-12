# Resilience Lab

A small orders service that keeps talking to MongoDB while you break things
underneath it. It generates a steady, rate-limited stream of reads and writes,
and reports — over HTTP — the latency, the errors, the retries the driver
performed on its own, and every topology change it observed.

You drive the disruption from the Atlas UI or CLI: a test failover, a tier
change, a pause and resume. The lab's job is to show what the *application*
felt while that happened.

The cluster is assumed to exist already (see `../../atlas-cluster-provisioning`).
Nothing here provisions, scales, or fails over anything, and every connection
comes from `MONGODB_URI`.

## What it measures

| Signal | Where it comes from |
|---|---|
| Write and read throughput, avg / p95 / max latency | timed in the workload loop, over a rolling window |
| Errors, grouped by exception type and server code | caught per operation, never raised |
| Driver retries | `CommandListener` — retryable failure arms a per-thread flag, the next command on that thread is the retry |
| Topology type changes, primary changes | `TopologyListener` |
| Current driver view of the replica set | `client.topology_description`, no command sent |

The workload deliberately has **no retry loop of its own**. Retryable writes
and retryable reads are the driver's machinery, so the retry behaviour on show
belongs to the driver, not to the lab.

## Layout

```
resilience-lab/
├── app/
│   ├── config.py      env-driven driver options + shared MongoClient
│   ├── metrics.py     MetricsStore, TopologyLogger, CommandCounter
│   ├── workload.py    rate-limited read/write generator
│   ├── seed.py        baseline orders so reads hit something on a cold start
│   ├── watch.py       polls /status, one line per second
│   └── main.py        FastAPI app
├── .env.example
└── requirements.txt
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/status` | window metrics, totals, errors, topology events, driver options |
| GET | `/health` | service liveness plus a live cluster `ping` (503 if unreachable) |
| GET | `/topology` | the driver's current view of the replica set |
| POST | `/load/pause`, `/load/resume` | stop and start the generator |
| POST | `/orders` | one write on demand — handy during a step-down |

## Setup

```bash
cd resilience-lab
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then paste your SRV string into MONGODB_URI
```

Every driver option that matters during a failover is an environment variable,
so the same experiment can be re-run with different settings and the numbers
compared. `RETRY_WRITES`, `HEARTBEAT_FREQUENCY_MS`, and
`SERVER_SELECTION_TIMEOUT_MS` are the three worth changing first.

## Live demo script

Copy-pasteable from a clean shell. `MONGODB_URI` is read from the environment,
so exporting it works whether or not you have created a `.env`.

```bash
export MONGODB_URI='your-atlas-connection-string'

cd v8-upgrade-resilience-ai-2026-08-13/resilience-lab

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# Optional — a baseline so the read path is exercised from the first tick
python app/seed.py --drop --count 2000

# Start the service (reads HOST/PORT; defaults to 127.0.0.1:8000)
python app/main.py
```

`app/` is a plain directory rather than a package, so if you prefer to invoke
uvicorn yourself, pass `--app-dir`:

```bash
uvicorn main:app --app-dir app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
curl -s http://127.0.0.1:8000/status | python3 -m json.tool
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/topology | python3 -m json.tool
```

For a projector, use the one-line-per-second view instead of raw JSON — new
topology events and errors are printed inline as they appear, so a primary
change lands in the same scroll as the latency it caused:

```bash
python app/watch.py
python app/watch.py --url http://127.0.0.1:8000 --interval 1
```

## Optional: Atlas Test Failover

Now cause the disruption from Atlas — **Cluster → … → Test Failover** — and
watch the `watch.py` output. Then drive the load by hand to probe recovery:

```bash
curl -s -X POST http://127.0.0.1:8000/load/pause
curl -s -X POST http://127.0.0.1:8000/orders        # one write, on demand
curl -s -X POST http://127.0.0.1:8000/load/resume
```

To show what the same failover costs *without* retryable writes, stop the
service and restart it with the lever flipped:

```bash
RETRY_WRITES=false python app/main.py
```

Tidy up when you are done:

```bash
python app/seed.py --clean
```

## Expected output

Abridged — hostnames, timings, and counts vary by cluster and by how you broke
it. During a test failover you should see the error count spike for a few
seconds, `driver_retries` increase, and a `primary_changed` event, followed by
throughput returning to the target rate.

```
time      w ops/s    w avg    w p95  r ops/s    r avg   err   err%  primary
14:22:01     5.03     18.4     31.2     4.97     11.1     0   0.0%  ...-00.mongodb.net:27017
14:22:09     4.71    412.8   2104.0     4.60     14.8     3   6.5%  none visible
          >> primary_changed: ...-00.mongodb.net:27017 -> none
          >> driver_retry: insert retried by the driver
          !! write error: NotWritablePrimary(10107)
14:22:14     5.01     22.7     44.9     5.02     12.0     0   0.0%  ...-01.mongodb.net:27017
          >> primary_changed: none -> ...-01.mongodb.net:27017
```

## Reusing this for another workshop

* Change `DB_NAME` / `ORDERS_COLLECTION` in `.env` to isolate parallel runs on a
  shared cluster.
* `WORKER_COUNT`, `TARGET_OPS_PER_SECOND`, and `READ_RATIO` shape the load;
  `METRICS_WINDOW_SECONDS` trades reaction speed for a smoother line.
* To watch a different command for retries, add its name to
  `CommandCounter.WATCHED` in `app/metrics.py`.

## Optional helper: `probe_opid.py`

There is an internal helper script `probe_opid.py` that can be used to experiment with how the lab classifies operations as retryable or not based on opIds and error codes.

It is **not** required for the primary live demo flow (`seed.py`, `main.py`, `watch.py`) and can be removed entirely if you prefer to keep the lab minimal. If you keep it, treat it as a scratchpad for deeper dives with engineers who want to see how retry classification works under the hood.
