# Hybrid Search Lab — see the query behind every result

An instructional lab that runs **keyword**, **semantic**, **hybrid**, and
**reranked** search side-by-side over the same movie collection — and, for every
result set, shows you the *exact* aggregation pipeline it ran so you can paste it
into `mongosh` and reproduce the result against your own cluster.

| Tab | Strategy | Atlas stage | What it shows |
|-----|----------|-------------|---------------|
| 🔤 Keyword | Atlas Search BM25 | `$search` | The baseline — literal word overlap, blind to meaning |
| 🧠 Semantic | Vector Search + Automated Embedding | `$vectorSearch` | Matches intent even when no words overlap |
| ⚡ Hybrid | Reciprocal Rank Fusion | `$rankFusion` | Fuses both rankings so exact *and* intent matches surface |
| 🎯 Reranked | Voyage AI cross-encoder | client-side | Re-scores the hybrid candidates so the best match lands first (optional) |

The whole lab uses **Atlas Automated Embedding (`autoEmbed`)**: Atlas embeds the
plot text at index time *and* embeds your query text at search time. That means
the semantic and hybrid queries take **plain natural-language text** — there is
no client-side embedding code and no API key in the query path. The `mongosh`
snippets the GUI shows you are therefore runnable verbatim. The one exception is
the optional **reranked** tab, whose final cross-encoder step runs client-side
via the Voyage AI API — the GUI is explicit about which part you can reproduce
in the shell and which part you cannot.

---

## Prerequisites

- Python 3.11+
- A MongoDB Atlas cluster provisioned by [`../atlas-cluster-provisioning`](../atlas-cluster-provisioning)
  with **Compute Auto-Scale enabled** — Atlas requires this to create an
  `autoEmbed` vector index. The provisioning lab's `.env.example` already sets
  `CLUSTER_COMPUTE_AUTOSCALE_ENABLED=true`.
- `mongosh` installed locally, to follow along in the shell.
- *(Optional)* A [Voyage AI](https://www.voyageai.com) API key — **only** for
  the 🎯 Reranked tab. The other three strategies need no key.

> This lab assumes the cluster already exists. It only loads data, creates
> search indexes, and queries them.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env: paste your cluster's SRV string into MONGODB_URI and add your
# DB_ADMIN_USER / password (from the atlas-cluster-provisioning output).
# (Optional) set VOYAGE_API_KEY if you want to try the 🎯 Reranked tab.
```

Every name the lab uses — database, collection, and both index names — lives in
`.env`, so the GUI, the setup scripts, and the `mongosh` snippets all stay in
sync. Change a name in one place and the whole lab follows.

### 3. Load the dataset (24 curated movies)

```bash
python scripts/load_data.py          # insert (skips if already present)
python scripts/load_data.py --drop   # wipe and reload from scratch
```

The dataset is tiny and self-contained (`data/movies.json`). The plots are
written so keyword search *misses* intent-based queries while semantic and
hybrid search find them — that contrast is the whole point of the lab.

### 4. Create the Atlas Search indexes

```bash
python scripts/create_indexes.py
```

This creates two indexes on the `plot` field:

- **`movies_vector_index`** — a `vectorSearch` index of type `autoEmbed`; Atlas
  owns the embeddings on both sides of the query.
- **`movies_text_index`** — a `search` (BM25) index for keyword matching.

### 5. Confirm both indexes are READY

Atlas builds indexes asynchronously. Wait 1–2 minutes, then:

```bash
python scripts/status.py
```

Re-run until both report `READY`. You can watch the same thing in the Atlas UI
under **Search Indexes**.

### 6. Run the GUI

```bash
streamlit run app.py
```

Pick a demo query (or type your own), click **Search**, and switch between the
four tabs. The left of each tab shows the ranked results; the right shows the
**"Run this yourself in mongosh"** panel and a stage-by-stage explanation.

---

## Good demo queries

These are pre-loaded in the app and chosen so keyword search stumbles while
semantic and hybrid succeed:

- `a story about overcoming loneliness`
- `something that will make me laugh`
- `people fighting to keep the lights on`
- `a journey across a dangerous landscape`
- `food brings a family back together`
- `uncovering a crime and doing the right thing`

Notice, for example, that *"people fighting to keep the lights on"* returns
**Blackout Protocol** semantically even though the plot never says "lights".

---

## Loading more movies

Each movie is just a `{title, year, genres, plot}` object, so you can grow the
collection three ways:

- **Load *N* real movies** from Atlas's built-in `sample_mflix` dataset — no
  files, no download:

  ```bash
  python scripts/load_data.py --sample 200 --drop
  ```

  This copies 200 random *real* movies that have a plot into the lab collection
  using a `$sample` aggregation (pure MongoDB — the same query you could run in
  `mongosh`). Load the sample data once from the Atlas UI first
  (**your cluster → ⋯ → Load Sample Dataset**); use `--source db.collection` to
  read from a different namespace. The pre-loaded demo queries are tuned for the
  curated set, so with real movies just type your own intent-based queries.

- **Edit the curated set** — append objects to `data/movies.json`, then reload:

  ```bash
  python scripts/load_data.py --drop
  ```

- **Load a separate file without touching the curated set** — point the loader
  at your own JSON array and append it:

  ```bash
  python scripts/load_data.py --file my_movies.json --append
  ```

Only the `plot` field is searched (it is both BM25- and vector-indexed), so make
the plots descriptive. Because the vector index uses Automated Embedding, Atlas
embeds each new plot **automatically** as soon as it is inserted — there is no
separate embedding step to run. Give it a few seconds, confirm with
`python scripts/status.py`, and the new movies appear in every tab.

---

## Follow along in mongosh

The GUI's **"Run this yourself in mongosh"** panel prints the exact pipeline for
whichever tab and query you are looking at. Connect once, then paste. Every
snippet below uses the query *"people fighting to keep the lights on"* — swap in
your own text and nothing else changes.

```bash
mongosh "$MONGODB_URI"
```

```javascript
use hybrid_search_lab
```

### 🔤 Keyword — `$search` (BM25)

Ranks documents purely by literal word overlap in `plot`.

```javascript
db.movies.aggregate([
  { $search: { index: "movies_text_index",
               text: { query: "people fighting to keep the lights on", path: "plot" } } },
  { $limit: 5 },
  { $project: { _id: 0, title: 1, year: 1, genres: 1, plot: 1,
                score: { $meta: "searchScore" } } }
])
```

Because no plot literally contains those words together, keyword search returns
weak or empty matches — exactly the gap semantic search closes.

### 🧠 Semantic — `$vectorSearch` over autoEmbed

You pass **plain text** in `query`; Atlas embeds it with the `autoEmbed` model
(`voyage-4`) and ranks by cosine similarity. No vector is computed client-side.

```javascript
db.movies.aggregate([
  { $vectorSearch: { index: "movies_vector_index", path: "plot",
                     query: "people fighting to keep the lights on",
                     model: "voyage-4", numCandidates: 100, limit: 5 } },
  { $project: { _id: 0, title: 1, year: 1, genres: 1, plot: 1,
                score: { $meta: "vectorSearchScore" } } }
])
```

**Blackout Protocol** — an engineer restarting the power grid — now ranks first,
matched on meaning rather than words.

### ⚡ Hybrid — `$rankFusion` (Reciprocal Rank Fusion)

Atlas runs the semantic and keyword pipelines, ranks each result set
independently, then fuses the ranks. Weights tune each leg's contribution.

```javascript
db.movies.aggregate([
  { $rankFusion: {
      input: { pipelines: {
        semantic: [ { $vectorSearch: { index: "movies_vector_index", path: "plot",
                        query: "people fighting to keep the lights on",
                        model: "voyage-4", numCandidates: 100, limit: 5 } } ],
        keyword:  [ { $search: { index: "movies_text_index",
                        text: { query: "people fighting to keep the lights on", path: "plot" } } },
                    { $limit: 5 } ]
      } },
      combination: { weights: { semantic: 1.0, keyword: 1.0 } },
      scoreDetails: true } },
  { $limit: 5 },
  { $project: { _id: 0, title: 1, year: 1, genres: 1, plot: 1,
                score: { $meta: "score" },
                scoreDetails: { $meta: "scoreDetails" } } }
])
```

Inspect `scoreDetails` on each returned document to see how much the semantic
and keyword legs each contributed to its fused rank — the clearest way to *see*
why hybrid ordering differs from either leg alone.

### 🎯 Reranked — Voyage AI cross-encoder (client-side)

This strategy is the exception to "follow along in mongosh". Hybrid search first
retrieves a wide candidate set (the query above, with a larger `limit`), then a
Voyage AI cross-encoder re-scores each candidate against the query. That second
step calls the Voyage API from the app — it has no `mongosh` equivalent.

```python
import voyageai
voyage = voyageai.Client()  # reads VOYAGE_API_KEY

# `candidates` are the plots returned by the hybrid query above
reranked = voyage.rerank(
    query=query,
    documents=[c["plot"] for c in candidates],
    model="voyage-rerank-2",
    top_k=5,
)
for item in reranked.results:
    print(round(item.relevance_score, 4), candidates[item.index]["title"])
```

Each result in the GUI shows its move, e.g. `hybrid #4 → rerank #1`, so you can
see exactly where the cross-encoder disagreed with the fused ranking.

---

## Architecture

```
data/movies.json  (24 curated movies)
    ↓ scripts/load_data.py
MongoDB Atlas  (hybrid_search_lab.movies)
    ↓ scripts/create_indexes.py
    ├── movies_vector_index  (Vector Search, type: autoEmbed, model: voyage-4, cosine)
    └── movies_text_index    (Atlas Search, BM25)

Streamlit app.py
    └── lib/search.py   → returns (results, pipeline) for each strategy
        ├── keyword_search   → $search
        ├── semantic_search  → $vectorSearch  (autoEmbed, plain-text query)
        ├── hybrid_search    → $rankFusion(semantic, keyword)
        └── rerank_search    → hybrid candidates → Voyage AI voyage-rerank-2 (client-side)
    └── lib/explain.py  → renders any pipeline as the mongosh snippet shown in the GUI
```

---

## Notes

- **Why autoEmbed?** It keeps the query surface identical between the GUI and
  `mongosh` — both send plain text. Without it, every semantic query in the
  shell would first need a client-side embedding step, breaking "follow along".
- **`$rankFusion`** is available on MongoDB 8.1+. If your cluster predates it,
  the keyword and semantic tabs still work; only the hybrid tab requires it.
- **Reranking is optional.** The 🎯 Reranked tab is the only strategy that needs
  `voyageai` installed and a `VOYAGE_API_KEY`, and the only one whose final step
  runs client-side rather than in Atlas. Skip it and the lab still fully
  demonstrates keyword vs. semantic vs. hybrid.
- **Cost** is negligible: 24 short plots to embed once at index time, plus one
  query embedding per semantic/hybrid search. Well within free-tier limits.
