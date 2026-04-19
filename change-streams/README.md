# Change Streams Demo (Python)

This demo walks through MongoDB Change Streams from scratch using the `sample_mflix.movies` collection that ships with every Atlas cluster.

---

## What is a Change Stream?

A **change stream** is a real-time feed of every write that happens on a MongoDB collection (or database, or entire cluster). Instead of polling the database on a schedule, your application opens a stream and MongoDB pushes each change event to you the moment it is committed.

```
Your App  ←──── change event ──────  MongoDB Atlas
               (insert / update /
                delete / replace)
```

Under the hood, change streams read MongoDB's **oplog** (the replication log). Because Atlas always runs as a replica set, the oplog is always available — no extra setup needed.

### When are change streams useful?

| Use case | Example |
|---|---|
| Real-time dashboards | Update a UI when inventory changes |
| Event-driven microservices | Trigger an order-fulfilment service when a new order is inserted |
| Cache invalidation | Evict a cached record the moment it is updated |
| Audit logging | Record every write to a separate audit collection |
| Data sync | Mirror changes to a secondary data store (Elasticsearch, Redis, etc.) |

---

## How a Change Event Looks

Every event delivered by a change stream is a document. Here is a simplified example of an **insert** event:

```json
{
  "_id": { "_data": "8266d3a1..." },   // ← resume token (explained later)
  "operationType": "insert",
  "ns": { "db": "sample_mflix", "coll": "movies" },
  "documentKey": { "_id": "..." },
  "fullDocument": {
    "title": "Neon Horizon",
    "year": 2024,
    "imdb": { "rating": 7.4 }
  }
}
```

An **update** event looks slightly different — it carries a `updateDescription` that tells you exactly which fields changed, rather than the whole document:

```json
{
  "operationType": "update",
  "documentKey": { "_id": "..." },
  "updateDescription": {
    "updatedFields": { "imdb.rating": 8.1, "imdb.votes": 15000 },
    "removedFields": []
  }
}
```

> **Tip:** You can ask MongoDB to also attach the full updated document by passing
> `full_document="updateLookup"` when opening the stream. That is what this demo does.

---

## Files

| File | Purpose |
|---|---|
| `watch.py` | Opens a change stream and prints events. Run this first. |
| `generate_changes.py` | Performs inserts, updates, and deletes to trigger events. Run this second. |
| `.env.example` | Environment variable template. |
| `requirements.txt` | Python dependencies. |

---

## Prerequisites

- Python 3.11+
- A MongoDB Atlas cluster with the **sample datasets** loaded
  (Atlas UI → `...` menu on your cluster → *Load Sample Dataset*)
- A database user with read/write access to `sample_mflix`

---

## Setup

1. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2. Create your `.env` file:

```bash
cp .env.example .env
```

3. Fill in `MONGODB_URI` with your Atlas connection string. The other values can stay as-is:

```env
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-host>/?retryWrites=true&w=majority
DB_NAME=sample_mflix
COLLECTION_NAME=movies
```

---

## The Demo (two terminals)

All four modes follow the same two-terminal pattern:

**Terminal 1** — start the watcher, then leave it running  
**Terminal 2** — run the change generator to trigger events

### Mode 1 — Watch everything

This is the baseline: every insert, update, and delete surfaces as an event.

**Terminal 1:**
```bash
python3 watch.py --mode 1
```

**Terminal 2:**
```bash
python3 generate_changes.py
```

Follow the prompts in Terminal 2. You will see six steps play out — three inserts, two updates, and two deletes — and each one will appear in Terminal 1 within milliseconds.

Expected Terminal 1 output (abridged):

```
--- Change Event ------------------------------------------
  Operation  : INSERT
  Namespace  : sample_mflix.movies
  DocumentId : 6659a1b4...
  Title      : Neon Horizon
  Year       : 2024
  IMDB       : 7.4 (10500 votes)
  Token      : 8266d3a1c4...

--- Change Event ------------------------------------------
  Operation  : UPDATE
  Namespace  : sample_mflix.movies
  DocumentId : 6659a1b4...
  Updated    : {"imdb.rating": 8.1, "imdb.votes": 15000}
  Full Doc   : 'Neon Horizon' (rating now: 8.1)
  Token      : 8266d3a2b1...
```

---

### Mode 2 — Inserts only

Adding a `$match` stage to the change stream pipeline tells MongoDB to deliver **only the events you care about**. The filtering happens on the server, so your application never even sees the unwanted events.

**Terminal 1:**
```bash
python3 watch.py --mode 2
```

**Terminal 2:**
```bash
python3 generate_changes.py
```

You will see exactly **3 events** (one per inserted movie). The two updates and the delete are silently filtered out by the server before they ever reach your application.

The pipeline used internally:

```python
pipeline = [
    {"$match": {"operationType": "insert"}}
]

collection.watch(pipeline)
```

---

### Mode 3 — Inserts + imdb.rating updates

You can match on the *contents* of an update, not just its type. This pipeline surfaces inserts and any update that touches `imdb.rating` — while ignoring the `awards` field update entirely.

**Terminal 1:**
```bash
python3 watch.py --mode 3
```

**Terminal 2:**
```bash
python3 generate_changes.py
```

You will see **4 events**: 3 inserts + the rating update. The `awards` update and both deletes are filtered out.

The pipeline used internally:

```python
pipeline = [
    {
        "$match": {
            "$or": [
                {"operationType": "insert"},
                {
                    "operationType": "update",
                    "updateDescription.updatedFields.imdb.rating": {"$exists": True},
                },
            ]
        }
    }
]
```

> **Why is this powerful?** In a real system you might have dozens of services each watching
> the same collection but with different filters. Each service only receives the events relevant
> to its own job.

---

### Mode 4 — Resume from a saved token

Every change event carries a **resume token** (`event["_id"]`). If your watcher crashes, restarts, or is intentionally stopped, you can hand that token back to MongoDB and the stream will pick up exactly where it left off — even if the gap was minutes ago.

This demo saves the latest token to `.resume_token` after every event in modes 1–3.

**Step 1** — Run mode 1 and let at least one event come through, then press Ctrl+C:

```bash
python3 watch.py --mode 1
# (wait for at least one event, then Ctrl+C)
```

**Step 2** — Run `generate_changes.py` again to produce more events after the token:

```bash
python3 generate_changes.py
```

**Step 3** — Resume from the saved token. All events that occurred *after* the saved token will be replayed immediately:

```bash
python3 watch.py --mode 4
```

The pipeline used internally:

```python
collection.watch(resume_after=token)
```

> **Why does this matter?** Change streams guarantee at-least-once delivery as long as you
> resume within the oplog window (24 hours by default on Atlas). You never miss an event,
> even if your service goes down briefly.

---

## Key Concepts Summary

| Concept | What it does |
|---|---|
| `collection.watch()` | Opens a change stream on that collection |
| `full_document="updateLookup"` | Attaches the full document to update events (extra read) |
| Pipeline (`$match`) | Filters events server-side before delivery |
| Resume token (`event["_id"]`) | A bookmark — store it and pass it to `resume_after=` to restart |
| `operationType` | One of: `insert`, `update`, `replace`, `delete`, `drop`, `rename` |

---

## Cleanup

`generate_changes.py` removes its demo documents at the end of each run (Step 6). If the script was interrupted before cleanup, run it again and it will tidy up at Step 1 before inserting new documents.

To manually remove any leftover documents, run this in mongosh:

```javascript
use sample_mflix
db.movies.deleteMany({ demoTag: "change-streams-demo-v1" })
```

---

## Troubleshooting

**`OperationFailure: The $changeStream stage is only supported on replica sets`**  
Change streams require a replica set or sharded cluster. Atlas clusters are always replica sets — if you see this error, you may be pointing at a standalone local MongoDB instance. Use Atlas instead.

**No events appear in the watcher**  
- Confirm both scripts are connected to the same cluster and the same `DB_NAME` / `COLLECTION_NAME`.
- Make sure you pressed Enter in `generate_changes.py` after starting the watcher.
- Check that your Atlas IP Access List allows connections from your current IP.

**`ValueError: Missing required environment variable: MONGODB_URI`**  
Your `.env` file is missing or the variable is not set. Run `cp .env.example .env` and fill in your connection string.
