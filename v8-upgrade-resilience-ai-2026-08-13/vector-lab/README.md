# Vector Search and Reranking Lab

One query, three strategies, side by side against a synthetic **DocsCo**
knowledge base. The point of the lab is the *gap between them*:

| Mode | Stage | What it can and cannot do |
|---|---|---|
| Keyword | `$search` (BM25) | Matches words. Cannot find an article that answers the question in different words. |
| Vector | `$vectorSearch` (cosine) | Matches meaning. Wording no longer has to line up, but related-but-wrong articles still crowd the top. |
| Vector + Rerank | `$vectorSearch` → cross-encoder | Scores each candidate against the query directly. Too slow to search with; ideal for reordering a shortlist. |

The cluster is assumed to exist already (see `../../atlas-cluster-provisioning`).
Nothing here provisions, scales, or deletes a cluster, and every connection
comes from `MONGODB_URI`.

All content is fictitious: DocsCo, its products (Ledger, Dispatch, Atlas
Reports, Signal, Vault), and its articles do not exist.

## The corpus is built to expose the gap

`data/build_corpus.py` generates 300 articles in three kinds, and the UI labels
each result so the audience can see which is which:

* **showcase** (6) — articles that genuinely answer an example query, written
  *without reusing the query's words*. "Why is my bill higher than last month?"
  is answered by *Understanding proration on mid-cycle plan changes*.
* **decoy** (3) — articles stuffed with a query's literal wording that answer a
  different question. BM25 loves them; the reranker demotes them.
* **filler** (291) — plausible support content, enough volume for
  `numCandidates` and BM25 scoring to behave realistically.

## Setup

```bash
cd vector-lab
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then paste your SRV string into MONGODB_URI
```

The database user needs `readWrite` on the lab database plus permission to
create Atlas Search indexes. Atlas Search and Atlas Vector Search require an
**M10 or larger** tier.

### Choosing an embedding backend

`EMBEDDING_PROVIDER` in `.env` picks one of three:

| Value | Key needed | Notes |
|---|---|---|
| `offline` | none | Local "concept hash" embeddings and a local pair scorer. No network, no cost. |
| `voyage` | `EMBEDDING_API_KEY` | Real embeddings and a real cross-encoder rerank. |
| `openai` | `EMBEDDING_API_KEY` | Real embeddings; rerank falls back to the offline scorer. |

`offline` exists so the lab runs in a room where handing out provider keys is
not practical. It is not a language model — it expands query tokens through a
small synonym table in `app/embeddings.py` and hashes them into buckets. That is
enough to reproduce the keyword-versus-vector gap honestly, but say so out loud:
**absolute scores from the offline backend mean nothing**, only the ordering is
instructive. Use `voyage` whenever relevance itself is the subject.

## Running

```bash
python data/build_corpus.py       # writes data/knowledge_base.json (deterministic)
python app/ingest.py              # embed and load; re-runnable
python app/indexes.py             # create both search indexes
python app/indexes.py --status     # poll until both report queryable
python app/main.py                # http://127.0.0.1:8001
```

Atlas builds search indexes asynchronously — wait for `--status` to show
`queryable` on both before searching, or the panels will return errors.

Other entry points:

```bash
python app/ingest.py --drop        # wipe and reload
python app/ingest.py --re-embed    # keep documents, recompute vectors
python app/indexes.py --drop       # required after changing EMBEDDING_DIM
python verify_offline.py           # exercise every module with no cluster at all
curl "http://127.0.0.1:8001/api/search?q=why+is+my+bill+higher&mode=all"
```

Changing `EMBEDDING_MODEL` or `EMBEDDING_DIM` invalidates both the stored vectors
and the index: `python app/indexes.py --drop`, then `--re-embed`, then recreate.

## The index definitions

Built by `app/indexes.py`; shown here because the definitions are the interesting
part of the setup.

```javascript
// kb_text_index — type: "search"
{ mappings: { dynamic: false,
              fields: { title: { type: "string" }, body: { type: "string" } } } }

// kb_vector_index — type: "vectorSearch"
{ fields: [ { type: "vector", path: "embedding",
              numDimensions: 1024, similarity: "cosine" },
            { type: "filter", path: "category" },
            { type: "filter", path: "product" } ] }
```

The two `filter` fields are not used by the default UI. They are there so a
workshop can add a pre-filter to the `$vectorSearch` stage and watch recall
change — a filter field must be in the index definition before it can be
filtered on.

## Example queries

Each is worded the way a person would actually ask, which is exactly why keyword
search struggles. Every result in the UI carries its `showcase` / `decoy` tag,
and reranked results show the move they made, e.g. `vector #11 → rerank #2`.

| Query | Keyword | Vector | + Rerank |
|---|---|---|---|
| *why is my bill higher than last month* | the decoy about sorting the bill list | finds *proration on mid-cycle plan changes*, but under the decoy | proration first |
| *we accepted the request but the other system never got it* | the "request / accepted" glossary decoy | finds *requests are accepted but nothing appears downstream* | the real answer first |
| *people cannot log in since IT changed something* | the password-policy decoy | finds the identity-provider article | provider article first |
| *the dashboard total does not match the file I downloaded* | partly works — the words overlap | finds the summary-versus-raw-stream article | unchanged |
| *everything slows down after lunch* | no article says "lunch" | finds the hourly-digest article | unchanged |
| *what happens to files when someone quits* | no article says "quits" | finds the teammate-leaves article | unchanged |

The last three are the honest cases where reranking has nothing to fix — worth
pointing out rather than hiding, since it is the reason to reach for a reranker
only when the candidate set is genuinely muddled.

## Layout

```
vector-lab/
├── data/
│   ├── topics.py            showcase / decoy / filler seeds, example queries
│   ├── build_corpus.py      deterministic generator
│   └── knowledge_base.json  generated, 300 articles
├── app/
│   ├── config.py            .env driven connection, namespace, provider
│   ├── embeddings.py        voyage / openai / offline backends
│   ├── rerank.py            voyage cross-encoder / offline pair scorer
│   ├── indexes.py           create, inspect, drop the two search indexes
│   ├── ingest.py            embed and load the corpus
│   ├── search.py            the three strategies, each returning its pipeline
│   ├── main.py              FastAPI entry point
│   └── templates/index.html the comparison UI
├── verify_offline.py        cluster-free check of every module
├── .env.example
└── requirements.txt
```

## Notes

* Embeddings are generated client-side, which keeps the lab explicit about what
  is sent where. Atlas `autoEmbed` removes that step entirely and leaves the
  `$vectorSearch` stage taking plain text — worth mentioning, not required here.
* `RERANK_CANDIDATES` must exceed `RESULT_LIMIT` or the reranker has nothing to
  reorder. The default fetches 40 and returns 8.
* Every panel can show the exact pipeline that produced it (`SHOW_PIPELINE`).
  The query vector is replaced by a placeholder so the page stays readable.

## Live demo script

Copy-pasteable from a clean shell. Everything is read from the environment, so
exporting works whether or not you have created a `.env`.

```bash
export MONGODB_URI='your-atlas-connection-string'

# The embedding backend. 'offline' needs no key at all — use it to rehearse.
export EMBEDDING_PROVIDER='voyage'
export EMBEDDING_API_KEY='your-embedding-provider-key'
export EMBEDDING_MODEL='voyage-3.5'
export EMBEDDING_DIM='1024'
export RERANK_MODEL='rerank-2'

cd v8-upgrade-resilience-ai-2026-08-13/vector-lab

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# 1. Generate the corpus — deterministic, so every attendee gets identical data
python data/build_corpus.py

# 2. Embed and load it into MongoDB
python app/ingest.py --drop

# 3. Create both Atlas Search indexes
python app/indexes.py

# 4. Atlas builds them asynchronously — wait for both to report queryable
python app/indexes.py --status

# 5. Serve the comparison UI on http://127.0.0.1:8001
python app/main.py
```

Step 4 is not optional. Searching before both indexes are queryable makes the
panels return errors, which looks like a broken lab rather than a slow index.
Re-run `--status` until both say `queryable`.

`app/` is a plain directory rather than a package, so if you prefer to invoke
uvicorn yourself, pass `--app-dir`:

```bash
uvicorn main:app --app-dir app --host 127.0.0.1 --port 8001
```

Then, in a second terminal, drive it from the command line:

```bash
curl -s http://127.0.0.1:8001/health
curl -s http://127.0.0.1:8001/api/config | python3 -m json.tool

# One query, all three strategies
curl -s "http://127.0.0.1:8001/api/search?q=why+is+my+bill+higher+than+last+month&mode=all" \
  | python3 -m json.tool

# Or one strategy at a time: keyword | vector | rerank
curl -s "http://127.0.0.1:8001/api/search?q=everything+slows+down+after+lunch&mode=keyword"
```

To rehearse the whole sequence with no provider key and no network calls to an
embedding API, set the backend to `offline` and repeat from step 2 — remember
that only the *ordering* is instructive in that mode:

```bash
export EMBEDDING_PROVIDER='offline' EMBEDDING_API_KEY='' EMBEDDING_DIM='1024'
python app/indexes.py --drop && python app/ingest.py --drop && python app/indexes.py
```

Changing `EMBEDDING_MODEL` or `EMBEDDING_DIM` invalidates both the stored
vectors and the vector index, so the drop-and-rebuild above is required, not
just tidy.

## Optional advanced topics

For deeper technical sessions, you can extend this lab into topics such as:

- Adding simple evaluation metrics (for example, logging which queries improved most when switching from keyword to vector or reranked search).
- Experimenting with different embedding models or index configurations and comparing latency/quality trade-offs.
- Introducing a lightweight cost or size comparison to illustrate why tiered or disaggregated approaches are interesting at larger scales.

These advanced topics are entirely optional and should only be included if you have additional time with a highly technical audience.

