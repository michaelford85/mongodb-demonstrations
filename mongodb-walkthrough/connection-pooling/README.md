# Connection Pooling

This demo benchmarks three connection patterns to make the cost of connection establishment visible and show why a shared MongoClient is essential at scale.

---

## Why connection pooling matters

Every new `MongoClient` instance must:
1. Resolve the Atlas SRV DNS record
2. Open TCP connections to cluster nodes
3. Complete TLS handshakes
4. Authenticate

This overhead is 50–200 ms per connection. Creating a new client per request is one of the most common MongoDB anti-patterns, and its cost compounds in multi-tenant deployments where many databases are accessed concurrently.

The fix is to create `MongoClient` **once at application startup** and reuse it for the lifetime of the process. The driver manages a connection pool internally and handles concurrent access safely.

---

## What the demo benchmarks

| Pattern | Description |
|---|---|
| **No pool** | New `MongoClient` created and closed for every query (anti-pattern) |
| **Pooled — sequential** | Single `MongoClient`, queries run one after another |
| **Pooled — concurrent** | Single `MongoClient`, queries dispatched across 10 threads simultaneously |

All three patterns run the same `find_one` workload against `sample_mflix.movies`.

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

## Expected output shape

```
Pattern                                    Total    Per op
────────────────────────────────────────── ──────── ───────
New client per operation (no pool)          18.40s   368ms
Shared pool — sequential                    1.20s    24ms
Shared pool — concurrent (10 threads)       0.18s    4ms
```

Pool reuse is typically **10–20× faster** than creating a new connection for every operation. Concurrent access with a shared pool compounds the advantage further.

---

## Key talking points

- `MongoClient` is thread-safe and designed to be a singleton — one instance per process
- In a multi-tenant setup, `client["tenant_a"]` and `client["tenant_b"]` both draw from the same pool; you do not need a separate client per tenant
- The default pool size is 100 connections; tune `maxPoolSize` to match your workload's concurrency
- Atlas connection limits are per-cluster tier — pool sizing on the application side directly determines how many Atlas connections your deployment consumes
