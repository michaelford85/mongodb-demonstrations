# Agentic AI with MCP + MongoDB Atlas (v1.0)

This repo is a **demo‑grade** (read: intentionally small + inspectable) reference for building an *agentic* app where:

- **OpenAI** does **reasoning + response synthesis**
- **MongoDB Atlas** is the **system of record** (documents), the **retrieval layer** (Vector Search), and the **memory store**
- **MCP (Model Context Protocol)** is the **tool interface** that makes data access explicit, inspectable, and auditable
- **VoyageAI** generates **embeddings** (both for backfilling datasets and for embedding “memory” at write time)

The philosophy for v1.0:

> **Tool‑first, LLM‑second.**  
> The LLM should *explain* results, not silently decide what data to fetch or invent data it never retrieved.

---

## What MongoDB brings to Agentic AI (in this demo)

### 1) A single “state layer” the agent can read and write
Traditional RAG demos treat a database as a read‑only knowledge base. Here, MongoDB also holds **agent state**:

- **`sample_mflix.movies`** and **`sample_mflix.comments`** are the agent’s “world knowledge” (sample datasets).
- **`mcp_config.agent_memory`** is the agent’s **long‑term memory** (preferences, constraints, facts the user wants remembered).

This is how you get an agent that can keep context **across** questions without relying on the LLM’s transient chat history.

### 2) Retrieval you can *measure*, not “vibes”
MongoDB Atlas Vector Search gives you:

- deterministic retrieval pipelines (`$vectorSearch` + `$project`)
- similarity scores you can log
- index + embedding field constraints you can verify in Atlas UI

That makes “agent correctness” something you can debug, not guess.

### 3) A clean boundary between *thinking* and *doing*
MCP turns “doing” into named tools with explicit inputs/outputs (e.g., `aggregate`, `insert-many`, `delete-many`).  
That’s critical for:

- debugging (“which tool did we call?”)
- safety (“what write operations are allowed?”)
- future multi‑tool routing (multiple MCP servers)

---

## Architecture (v1.0)

```text
User
  └── demo_mcp_agent_http_simple.py
       ├── OpenAI (LLM) .............. response synthesis + reasoning
       ├── VoyageAI .................. embeddings for queries + memory text
       └── MCP over HTTP (JSON-RPC) .. structured DB tool calls
            └── MongoDB MCP Server
                 ├── aggregate (vectorSearch over movies)
                 ├── aggregate (vectorSearch over agent_memory)
                 ├── insert-many (save memory)
                 └── delete-many (clear memory)
```

---

## Repository layout (expected)

```text
agentic-ai-with-mcp/
  demo_mcp_agent_http_simple.py
  scripts/
    start_mcp_server.sh
  voyageai-vector-embeddings/
    01_create_memory_collection.py
    02_backfill_movie_embeddings.py
    03_backfill_comment_embeddings.py
    04_backfill_memory_embeddings.py
    05_create_vector_search_indexes.py
  requirements.txt
  .env              # not committed
```

---

## Prerequisites

- Python 3.10+
- Node.js 18+ (for `npx` / `mongodb-mcp-server`)
- A MongoDB Atlas cluster with the sample dataset **`sample_mflix`** available
- API keys:
  - `OPENAI_API_KEY`
  - `VOYAGE_API_KEY` (VoyageAI embeddings)
  - Atlas / MCP credentials required by your MongoDB MCP server configuration

---

## Environment variables (.env)

Create `agentic-ai-with-mcp/.env` (do **not** commit it). Example:

```env
# --- OpenAI ---
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5

# --- VoyageAI (client-side embedding generation) ---
VOYAGE_API_KEY=...
VOYAGE_MODEL=voyage-4
VOYAGE_OUTPUT_DIM=1024

# --- MongoDB MCP Server transport (HTTP) ---
MDB_MCP_TRANSPORT=http
MDB_MCP_HTTP_PORT=3000
MDB_MCP_SERVER_URL=http://127.0.0.1:3000/mcp

# Enable Atlas Search / Vector Search tools in MCP (required)
MDB_MCP_PREVIEW_FEATURES=search

# If you want MCP server-side auto-embedding support, this is used by the MCP server
# (This demo uses Voyage client-side embedding for queryVector and memory writes.)
MDB_MCP_VOYAGE_API_KEY=...

# --- Demo config ---
MEMORY_DB=mcp_config
MEMORY_COLLECTION=agent_memory
MOVIES_DB=sample_mflix
MOVIES_COLLECTION=movies

# Atlas Search / Vector Search index names
MEMORY_VECTOR_INDEX=memory_voyage_v4
MOVIES_VECTOR_INDEX=movies_voyage_v4

# Embedding field name used in the collections + indexes
EMBEDDING_FIELD=embedding_voyage_v4
```

Optional debug toggles for the client (leave unset normally):

```env
# Print every MCP tool call (tool name + args)
SHOW_TOOLS=1

# Print retrieved memory snippets (what will be injected into the LLM prompt)
SHOW_MEMORY=1
```

---

## Step-by-step: build the collections, embeddings, and indexes

The following scripts match the flow in your project directory:

1. **Create the memory collection** (`mcp_config.agent_memory`)
2. **Backfill embeddings** for `sample_mflix.movies`
3. **Backfill embeddings** for `sample_mflix.comments`
4. **Backfill embeddings** for `mcp_config.agent_memory` (optional seed data)
5. **Create Atlas Vector Search indexes** for the above collections

From the repo root (with your venv activated):

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Then run these scripts **in order**:

```bash
python voyageai-vector-embeddings/01_create_memory_collection.py
python voyageai-vector-embeddings/02_backfill_movie_embeddings.py
python voyageai-vector-embeddings/03_backfill_comment_embeddings.py
python voyageai-vector-embeddings/04_backfill_memory_embeddings.py
python voyageai-vector-embeddings/05_create_vector_search_indexes.py
```

### What each script does (why it matters)

#### 01_create_memory_collection.py
Creates `mcp_config.agent_memory` and (if needed) any basic schema/index setup so the agent has somewhere to persist “remember …” facts.

#### 02_backfill_movie_embeddings.py
Adds `embedding_voyage_v4` vectors to `sample_mflix.movies`.
This makes “recommend movies like X” a **vectorSearch** problem (semantic similarity), not keyword matching.

#### 03_backfill_comment_embeddings.py
Same as movies, but for `sample_mflix.comments`.
Useful for later iterations (e.g., “summarize what people said about Movie Y”).

#### 04_backfill_memory_embeddings.py
Optional seed: you can preload memory documents (or run to update existing memory docs).
In v1.0 the demo also embeds memory at write time (when the user types `remember …`).

#### 05_create_vector_search_indexes.py
Creates Atlas Vector Search indexes (example names used throughout this repo):

- `sample_mflix.movies` → `movies_voyage_v4`
- `sample_mflix.comments` → `comments_voyage_v4`
- `mcp_config.agent_memory` → `memory_voyage_v4`

In Atlas UI you should see indexes in **Search & Vector Search** and each should show “READY”.

---

## Start the MongoDB MCP server (HTTP)

This demo assumes your MCP server is exposed over HTTP at:

- `http://127.0.0.1:3000/mcp`

Start it via your script:

```bash
./scripts/start_mcp_server.sh
```

Sanity checks:

```bash
# Port open?
nc -vz 127.0.0.1 3000

# MCP endpoint responds (it will not be a normal GET endpoint)
curl -i http://127.0.0.1:3000/
curl -i http://127.0.0.1:3000/mcp
```

> Note: `/mcp` is JSON‑RPC, so a plain GET won’t return “app data”. The important part is that the port is reachable and the client can initialize.

---

## Run the demo client

The demo client script should be named exactly:

- `demo_mcp_agent_http_simple.py`

Run:

```bash
python demo_mcp_agent_http_simple.py
```

If you want to see tool calls + memory retrieval:

```bash
SHOW_TOOLS=1 SHOW_MEMORY=1 python demo_mcp_agent_http_simple.py
```

---

## CLI commands (in the demo)

Inside the interactive prompt:

- `remember <text>`  
  Saves a memory document to `mcp_config.agent_memory` **and** embeds it using VoyageAI into `embedding_voyage_v4`.

- `clear`  
  Deletes memory documents created by the demo client (so you can re-run flows cleanly).

- `exit`  
  Quit.

---

## Demo questions (a good test sequence)

Use these **in order** to prove each capability:

### A) Prove the LLM is working (no tools required)
1. `What is MCP in the context of AI tooling? Explain in 2 sentences.`

### B) Prove memory write → MongoDB (insert-many)
2. `remember I like philosophical sci-fi with simulated reality themes.`

### C) Prove memory retrieval → prompt injection (vectorSearch over agent_memory)
3. `What kind of movies do I like? Answer in 1 sentence.`  
   - With `SHOW_MEMORY=1`, you should see the retrieved memory snippet printed.

### D) Prove movie retrieval uses MongoDB Vector Search (aggregate + $vectorSearch)
4. `Recommend 5 movies I'd like. Give title + genres + 1 sentence why.`

### E) Prove memory changes the output (save another preference)
5. `remember I dislike excessive gore and torture.`  
6. `Recommend 5 movies I'd like. Avoid gore.`

### F) Prove clear works (delete-many) and retrieval changes
7. `clear`  
8. `Recommend 5 movies I'd like.`  
   - With cleared memory, the response should lose those preference constraints.

---

## How routing works in v1.0 (and what “agentic” means here)

This version is **deliberately deterministic**:

- The Python client decides whether to call:
  - memory retrieval (`agent_memory` vector search)
  - movie retrieval (`movies` vector search)
  - memory write (`insert-many`)
  - memory clear (`delete-many`)
- The LLM **does not** choose tools in v1.0.
- The LLM is used after retrieval to format results and explain the “why” in a user-friendly way.

That design makes it easy to verify:
- which tool ran,
- with what inputs,
- and what came back.

---

## Demonstration Cleanup

Run the following python script to:
- Load config from your local `.env` file
- Drop Atlas Vector Search indexes:
  - `COMMENTS_VECTOR_INDEX`
  - `MEMORY_VECTOR_INDEX`
  - `MOVIES_VECTOR_INDEX`
- Unset the `EMBEDDING_FIELD` from `sample_mflix.comments` and `sample_mflix.movies`
- Drops `MEMORY_DB` database (which also wipes the `MEMORY_COLLECTION` collection)

```bash
python voyageai-vector-embeddings/06_cleanup_mcp_demo.py
```

---

## Roadmap (future iterations)

Planned upgrades after v1.0:

- **Faster retrieval**: caching, fewer candidates, smaller projections, and batched calls
- **Token-aware prompts**: tighter prompt templates and selective memory injection
- **Smarter routing**: move from keyword heuristics → LLM tool selection with guardrails
- **Multiple MCP servers**: planner that chooses between MongoDB, filesystem, web, etc.
- **Hybrid search**: combine keyword + vector search for robustness

---

## Release / tag v1.0

```bash
git add README.md demo_mcp_agent_http_simple.py
git commit -m "Demo-grade MCP + MongoDB agent (v1.0)"
git tag v1.0
git push origin main --tags
```

---

## Troubleshooting

### “No memory retrieved” even though documents exist
Common causes:
- embedding field name mismatch (`EMBEDDING_FIELD` vs what’s in Atlas)
- index name mismatch (`MEMORY_VECTOR_INDEX`)
- vector dimension mismatch (`VOYAGE_OUTPUT_DIM` vs index dimensions)
- memory retrieval uses a query that doesn’t match your stored text (try: `What do I like?`)

Run with:

```bash
SHOW_TOOLS=1 SHOW_MEMORY=1 python demo_mcp_agent_http_simple.py
```

and confirm you see an `aggregate` call against `mcp_config.agent_memory` using `$vectorSearch`.

### Voyage authentication errors
If backfill scripts fail with `voyageai.error.AuthenticationError`, double-check `VOYAGE_API_KEY`.  
(Your `output.txt` showed this exact failure mode earlier.)

---

**v1.0 principle (repeatable + debuggable):**  
MongoDB provides *state + retrieval*, MCP provides *tool transparency*, and the LLM provides *explanations*.
