# Agentic AI with MCP (MongoDB Demonstration)

This directory demonstrates an **agentic AI workflow using MongoDB + MCP (Model Context Protocol)**.
The focus of this demo is showing how an AI agent can:

- Reason over data using MongoDB tools
- Perform multi-step analysis (semantic retrieval + aggregation)
- Persist **agent memory** back into MongoDB
- Safely operate using MCP Inspector for observability and control

This demo intentionally uses **public MongoDB sample datasets** (e.g. `sample_mflix`) and **ephemeral MCP services** so it can be reproduced easily and safely.

---

## High-level Architecture

- **MongoDB Atlas** – system of record + vector search + memory storage
- **mongodb-mcp-server** – exposes MongoDB capabilities via MCP (run ephemerally via `npx`)
- **MCP Inspector** – observability, debugging, and safety controls
- **Python** – local orchestration, embeddings, and demo utilities
- **VoyageAI** – vector embeddings (Voyage v4 family)

> The `mongodb-mcp-server` is **not vendored into this repository**. It is launched ephemerally via `npx` during the demo.

---

## Prerequisites

- Python 3.10+
- Node.js 18+ (with `npx` available)
- Access to a MongoDB Atlas project
- MongoDB Atlas API credentials (service account)
- VoyageAI API key (for embeddings)

---

## Environment Variables (`.env`)

Create a `.env` file in **this directory** (`agentic-ai-with-mcp/`).  
This file is intentionally **not committed to git**.

```env
# MongoDB Atlas API credentials
MDB_MCP_API_CLIENT_ID=your_atlas_client_id
MDB_MCP_API_CLIENT_SECRET=your_atlas_client_secret

# Enable Atlas Search / Vector Search tools
MDB_MCP_PREVIEW_FEATURES=search

# VoyageAI API key (for vector embeddings)
MDB_MCP_VOYAGE_API_KEY=your_voyage_api_key

# Require confirmation for write / destructive tools
MDB_MCP_CONFIRMATION_REQUIRED_TOOLS=insert-many,update-many,delete-many,drop-collection,drop-database
```

---

## Python Virtual Environment Setup

All Python work for this demo is isolated to a local virtual environment.

From `agentic-ai-with-mcp/`:

```bash
python -m venv .venv
source .venv/bin/activate
```

Upgrade pip and install dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## `requirements.txt`

Create a `requirements.txt` file in this directory with the following contents:

```txt
mcp[cli]
pymongo
voyageai
python-dotenv
```

These packages are used for:

- MCP client utilities and CLI
- MongoDB access from Python
- Embedding backfill scripts
- Local orchestration and experimentation

---

## Running the MCP Inspector with MongoDB MCP Server

The MongoDB MCP server is launched **ephemerally** via `npx` and inspected using the MCP Inspector.

### Step 1: Load environment variables

```bash
set -a
source .env
set +a
```

### Step 2: Start MCP Inspector + MongoDB MCP Server

```bash
npx -y @modelcontextprotocol/inspector   npx -y mongodb-mcp-server@latest --readOnly=false
```

This will:

- Start the **MCP Inspector UI** (typically at http://localhost:6274)
- Launch `mongodb-mcp-server` over STDIO
- Expose MongoDB tools (find, aggregate, insert, vector search, etc.) to the Inspector

---

## Demo Focus: Agent Memory

This demo emphasizes **agentic behavior**, specifically:

1. Retrieve similar "cases" (e.g. `sample_mflix.comments`) using semantic meaning
2. Verify patterns using MongoDB aggregations
3. Persist conclusions into a dedicated memory collection (e.g. `mcp_config.investigations`)
4. Recall and compare past investigations in follow-up interactions

All memory writes are gated via MCP confirmation controls.

---

## Notes on Ephemeral Dependencies

- `mongodb-mcp-server` is **not cloned into this repository**
- It is executed via `npx` for:
  - Clean demos
  - Reproducibility
  - No vendored Node dependencies
- You may clone the server **outside this repo** for inspection or debugging, but it is not required

---

## Cleanup

When the demo is complete:

- Stop the MCP Inspector process
- Deactivate the Python virtual environment
- Optionally delete the `.venv/` directory

No permanent services or infrastructure changes are required.

---

## Repository Intent

This repository is intended to demonstrate **how agentic AI systems can safely reason, act, and remember using MongoDB as a core system of record** — not to serve as a production application.
