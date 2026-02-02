# Agentic AI with MCP + MongoDB (v1.0)

This repository demonstrates a **demo-grade Agentic AI system** built on top of:

- **MongoDB Atlas** (memory, retrieval, grounding)
- **Model Context Protocol (MCP)** (tool interface)
- **OpenAI** (reasoning + language)
- **VoyageAI** (embeddings)

The goal of **v1.0** is to show—clearly, deterministically, and without magic—how **MongoDB can act as the long-term cognitive substrate for agentic AI systems**.

---

## Versioning

This release: `v1.0`

## What This Demo Is (and Is Not)

### ❌ This is NOT:
- A black-box autonomous agent
- Prompt-only “tool calling”
- A hallucination-prone RAG demo
- An LLM that pretends to have memory

### ✅ This IS:
- A **tool-first agent**
- With **explicit routing logic**
- Using **real vector search**
- Where **MongoDB stores memory and facts**
- And the **LLM only reasons over retrieved data**

---

## Why MongoDB for Agentic AI

Agentic AI requires **persistent, queryable, evolvable state**.

MongoDB is uniquely suited to fill this role.

---

### 1. MongoDB as Long-Term Agent Memory

The agent stores memory as documents in MongoDB:

- User preferences
- Learned constraints
- Facts the agent should remember across turns

Each memory:
- Is embedded using **VoyageAI**
- Stored in `mcp_config.agent_memory`
- Indexed with **Atlas Vector Search**
- Retrieved semantically (not via keywords)

This allows the agent to remember **meaning**, not just strings.

---

### 2. MongoDB as the Agent’s World Model

The agent does not “improvise” answers.

Instead:
- It queries MongoDB through MCP tools
- MongoDB returns grounded results
- The LLM explains *why* those results matter

In this demo:
- Movies come from `sample_mflix.movies`
- Memory comes from `agent_memory`
- The LLM never invents movie data

MongoDB is the **source of truth**.

---

### 3. Deterministic, Inspectable Agent Behavior

This demo intentionally avoids “LLM-decides-everything” routing.

Instead:
- The **Python client decides when tools are used**
- Tool usage is **explicit and logged**
- The LLM never silently calls tools

This yields:
- Predictable behavior
- Lower token usage
- Easier debugging
- Production-friendly architecture

---

## Architecture Overview

User
└── Python Agent Client
├── OpenAI (reasoning + explanation)
├── VoyageAI (query + memory embeddings)
├── MCP HTTP Client
│    └── MongoDB MCP Server
│         ├── Vector Search: movies
│         └── Vector Search: agent_memory
└── MongoDB Atlas

**Key principle:**

> MongoDB decides facts.  
> The LLM explains them.

---

## Key Technologies and Roles

### OpenAI (LLM)
Used for:
- Natural language understanding
- Reasoning over retrieved data
- Producing final user-facing answers

Not used for:
- Memory storage
- Search
- Data authority

---

### VoyageAI (Embeddings)
Used for:
- Embedding user queries
- Embedding agent memory

Embeddings are:
- Generated client-side
- Stored explicitly
- Queried via Atlas Vector Search

---

### MongoDB Atlas
Provides:
- Persistent agent memory
- Vector similarity search
- Schema flexibility for evolving agents
- One system for short- and long-term state

Collections used:
- `sample_mflix.movies`
- `mcp_config.agent_memory`

---

### Model Context Protocol (MCP)
MCP provides:
- A standardized tool interface
- Clear separation between agent logic and data systems
- Inspectable request/response boundaries

This demo uses **MCP over HTTP JSON-RPC**.

---

## Demo Script

Primary script:
```
demo_mcp_agent_http_simple.py
```

Capabilities:
- General Q&A via OpenAI
- Persistent memory via MongoDB
- Vector search over movies
- Deterministic tool routing
- Explicit memory clear/reset

---

## Commands

remember    # store long-term memory (embedded + indexed)
clear             # delete all agent memory
exit              # quit

Optional debugging flags:

SHOW_TOOLS=1      # log MCP tool usage
SHOW_MEMORY=1     # log retrieved memory

## Example Demo Flow

What is MCP?
remember I like philosophical sci-fi with simulated reality themes.
Recommend 5 movies I’d like.
remember I dislike excessive gore.
Recommend 6 movies grouped by vibe.
clear
Recommend 5 movies again.

You can observe:
- When memory is written
- When memory is retrieved
- When vector search is invoked
- How behavior changes when memory is cleared

---

## Why This Pattern Matters

This repo demonstrates a **production-oriented agentic AI pattern**:

| Concern | Responsibility |
|------|--------------|
| Memory | MongoDB |
| Retrieval | MongoDB Vector Search |
| Tooling | MCP |
| Reasoning | LLM |
| Control | Application code |

This avoids:
- Prompt bloat
- Hidden agent state
- Unbounded token growth
- Tool hallucination

---

## Roadmap (Future Versions)

Planned enhancements:
- LLM-assisted agent planning
- Token-aware routing
- Hybrid keyword + vector search
- Multiple MCP servers
- Faster retrieval paths
- Smarter memory prioritization

---