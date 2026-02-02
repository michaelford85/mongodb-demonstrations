# Agentic AI with MCP + MongoDB (v1.0)

This repository demonstrates a **demo‑grade agentic AI client** built on:

- **OpenAI** – LLM reasoning and response synthesis  
- **VoyageAI** – client‑side embedding generation  
- **MongoDB Atlas** – vector search + persistent agent memory  
- **MCP (Model Context Protocol)** – structured, inspectable tool invocation over HTTP  

The emphasis of v1.0 is **clarity, determinism, and observability**.

---

## What This Demo Shows

### Deterministic Tool Usage
The Python client decides *when* to call MCP tools based on user intent (keywords + routing logic), not LLM hallucination.

Enable visibility with:
```bash
SHOW_TOOLS=1 SHOW_MEMORY=1 python demo_mcp_agent_http_simple.py
```

---

### Persistent Agent Memory
User preferences are embedded with VoyageAI and stored in MongoDB Atlas.
They are retrieved via vector similarity and injected into the LLM prompt.

---

### Tool‑First, LLM‑Second
The LLM never invents results.
All recommendations come from MongoDB queries.

---

## Architecture

```
User
 └── Python Client
      ├── VoyageAI (embeddings)
      ├── MCP HTTP Client
      │    └── MongoDB MCP Server
      │         ├── movies vector search
      │         └── agent_memory vector search
      └── OpenAI (response synthesis)
```

---

## Setup

### Start MCP Server
```bash
./scripts/start_mcp_server.sh
```

### Run Demo
```bash
python demo_mcp_agent_http_simple.py
```

Optional debugging:
```bash
SHOW_TOOLS=1 SHOW_MEMORY=1 python demo_mcp_agent_http_simple.py
```

---

## Environment Variables

```env
OPENAI_API_KEY=...
VOYAGE_API_KEY=...
VOYAGE_MODEL=voyage-4
VOYAGE_OUTPUT_DIM=1024

MDB_MCP_TRANSPORT=http
MDB_MCP_HTTP_PORT=3000
MDB_MCP_SERVER_URL=http://127.0.0.1:3000/mcp
```

---

## Commands

```
remember <text>
clear
exit
```

---

## Demo Flow

1. What is MCP?
2. remember I like philosophical sci‑fi with simulated reality themes.
3. Recommend 5 movies I’d like.
4. remember I dislike excessive gore.
5. Recommend 6 movies, grouped by vibe.
6. clear
7. Recommend 5 movies again.

---

## Roadmap

- Faster hybrid search
- Token‑aware routing
- Smarter agentic planning
- Multiple MCP servers

---

## Release

```bash
git tag v1.0
git push origin v1.0
```

---

**Principle:**  
The LLM explains results — it never decides what data to fetch.
