# Leafy Bank — Ansible Automation

Ansible playbooks for deploying the [Leafy Bank](https://github.com/mongodb-industry-solutions/leafy-bank-ui) demo application locally using Docker. Leafy Bank is a MongoDB Financial Services reference implementation: a Next.js frontend backed by a constellation of Python microservices that showcase Atlas features like multi-document ACID transactions, Vector Search, Time Series collections, and agentic AI workflows.

Rather than cloning nine repositories and hand-crafting `.env` files, this automation:

- Clones each selected backend service repo and the UI.
- Generates a correctly wired `.env` / `.env.local` from a single secrets file.
- Creates required MongoDB databases and collections automatically.
- Builds and starts every container via Docker Compose.

---

## Architecture

```
Leafy Bank UI  (Next.js, port 3000)
├── Accounts Service                        port 8080  [core]
├── Transactions Service                    port 8001  [core]
├── Chatbot / PDF-RAG                       port 8002  [optional]
├── Open Finance Service                    port 8003  [optional]
├── Capital Markets — Loaders               port 8004  [optional]
├── Capital Markets — Agents               port 8005  [optional]
├── Capital Markets — Market Assistant      port 8006  [optional]
├── Capital Markets — Crypto Assistant      port 8007  [optional]
└── Capital Markets — MCP Interaction       port 8008  [optional, standalone UI]
```

All services connect to your existing **MongoDB Atlas** cluster.

---

## Demo Walkthrough

Leafy Bank is structured as three progressive tiers. Each tier introduces new MongoDB capabilities on top of the last. Deploy only what you need for a given conversation.

---

### Tier 1 — Core Banking (Accounts + Transactions)

**Deploy:**
```bash
ansible-playbook site.yml
```

Select any demo user from the welcome screen at `http://localhost:3000`, then explore:

- **Account management** — open and close accounts, view balances and account cards. The document model stores the full account record as a single BSON document, eliminating joins and making reads fast.
- **Transfers and digital payments** — send money between demo users. Each payment touches multiple collections atomically. This is the **multi-document ACID transaction** story: either all writes commit or none do, with no partial state visible to other operations.
- **Transaction history** — drill into a recent transaction to see the raw MongoDB document. Useful for showing how naturally financial data maps to documents vs. relational rows.

**MongoDB capabilities on show:**
| Capability | Where you see it |
|---|---|
| Flexible document model | Account and user records — no rigid schema |
| Multi-document ACID transactions | Every transfer / payment |
| Real-time reads | Balances update immediately after a transaction |

---

### Tier 2 — Open Finance

**Deploy:**
```bash
ansible-playbook site.yml -e "deploy_services=[accounts,transactions,openfinance]"
```

- **Open Finance** — connect to simulated external institutions. The service aggregates accounts and products (loans, mortgages) from multiple sources into a unified financial summary. Demonstrates **aggregation pipelines** combining heterogeneous data and MongoDB's **BSON/JSON compatibility** with external APIs — no serialisation layer needed.

**MongoDB capabilities on show:**
| Capability | Where you see it |
|---|---|
| Aggregation pipelines | Global financial summary across internal + external accounts |
| Flexible schema | Heterogeneous external account/product documents in one collection |

---

### Tier 2b — Personal Banking Assistant (PDF RAG)

Source: [cross-backend-pdf-rag](https://github.com/mongodb-industry-solutions/cross-backend-pdf-rag)

**One-time setup — generate the source document:**
```bash
python3 scripts/generate_chatbot_pdf.py
```
This creates a Leafy Bank Terms & Conditions PDF and places it where the Docker build expects it. You can substitute any PDF of your own by setting `chatbot_pdf_path` in `vars/secrets.yml` to its absolute path.

**Deploy** (can be added to any tier):
```bash
ansible-playbook site.yml -e "extra_services=[chatbot]"
```

**Open at:** `http://localhost:3000` — navigate to the Personal Assistant chat icon in the UI.

The chatbot is a classic **Retrieval-Augmented Generation (RAG)** pipeline, in contrast to the agentic ReAct pattern used by the Capital Markets assistants:

1. **Ingest** — on first startup the service chunks the PDF into overlapping text segments, converts each page to an image for visual display, and stores both in the `leafy_bank_pdf_rag` MongoDB database.
2. **Embed** — each chunk is embedded using Amazon Bedrock's **Cohere `embed-english-v3`** model (1536 dimensions) and stored as a vector in Atlas.
3. **Retrieve** — when a user asks a question, the query is embedded with the same model and the nearest chunks are retrieved via **Atlas Vector Search**.
4. **Generate** — the retrieved chunks are injected into the prompt context and **Claude Haiku** (via Bedrock) generates a concise, grounded answer. The relevant PDF page image is shown alongside the response.

**Example questions to ask:**
- *"What is the daily wire transfer limit?"*
- *"How much does an overdraft cost?"*
- *"What is the APY on the High-Yield Savings account?"*
- *"What happens if I report my card stolen?"*
- *"How long does Leafy Bank keep my data?"*

**MongoDB capabilities on show:**
| Capability | Where you see it |
|---|---|
| **Atlas Vector Search** | Semantic retrieval of relevant document chunks at query time |
| **Document model** | PDF chunks, page images, and embeddings stored together as BSON documents |
| **Flexible schema** | Superduper framework stores heterogeneous artifact types (text, binary images, vectors) in one collection |

> **AWS credentials required** — Bedrock is used for both embedding and chat completion. Add `aws_*` to `vars/secrets.yml` before deploying. The same credentials used for Capital Markets services work here.

---

### Tier 3 — Capital Markets & Agentic AI ⭐

> **This is the recommended tier for showcasing MongoDB's Agentic AI capabilities.**
> MongoDB acts as the data layer for agent reasoning, planning, memory, and tool use —
> not just storage.

**Deploy:**
```bash
ansible-playbook site.yml -e "deploy_services=[accounts,transactions,openfinance,cm-loaders,cm-agents,cm-market-assistant,cm-crypto-assistant,cm-mcp]"
```

> **Data dependency:** After deployment, trigger `cm-loaders` to run a data load cycle
> before using the agents and assistants. The loaders populate the market data collections
> that agents read from. Without this step, agent responses will be empty.

#### What to explore

- **Market & Crypto portfolios** — view pre-built investment portfolios for traditional assets (stocks, ETFs) and cryptocurrency. Data is ingested from Yahoo Finance, Binance, FRED, and CoinGecko and stored in **Time Series collections** — optimised for high-frequency market data.

- **Scheduled Agents** (`cm-agents`, port 8005) — six specialised AI agents run on a schedule, each analysing a different signal: price trends, financial news sentiment, and social media sentiment for both traditional and crypto assets. Reports are stored in MongoDB and retrieved via **Atlas Vector Search** using the `voyage-finance-2` finance-domain embedding model.

- **Market Assistant & Crypto Assistant** (`localhost:3000`) — ReAct (Reason and Act) conversational agents built with LangGraph. Ask natural language questions about portfolios, market conditions, or asset allocation. Source: [Market Assistant](https://github.com/mongodb-industry-solutions/leafy-bank-backend-capitalmarkets-react-agent-chatbot) · [Crypto Assistant](https://github.com/mongodb-industry-solutions/leafy-bank-backend-capitalmarkets-react-agent-crypto).

- **MCP Interaction** (`http://localhost:8008`) — a standalone UI that showcases MongoDB as a first-class AI tool via the Model Context Protocol. Open this for the clearest view of MongoDB's role in an agentic system. Source: [leafy-bank-capitalmarkets-mcp](https://github.com/mongodb-industry-solutions/leafy-bank-capitalmarkets-mcp).

#### Where MongoDB powers the AI agent

| MongoDB capability | Role in the agent |
|---|---|
| **Time Series collections** | Stores market and crypto price history for agent analysis |
| **Atlas Vector Search** | Semantic retrieval of agent-generated reports using finance-domain embeddings |
| **Agent memory (LangGraph checkpointer)** | Full agent state — reasoning steps, tool calls, intermediate results — is persisted to MongoDB after every interaction, enabling true multi-turn conversations |
| **Document model for agent state** | Complex nested agent state maps naturally to BSON with no ORM or schema migration |
| **MongoDB MCP Server** | Agents query Atlas via JSON-RPC without a MongoDB driver — standardised, observable, and read-only enforced |
| **Scheduled writes** | Loaders and agent report generation run on a timer, continuously updating the knowledge base |

---

### Tier 3b — MCP Interaction *(standalone, best for AI demos)*

**Deploy** (can be added to any tier):
```bash
ansible-playbook site.yml -e "extra_services=[cm-mcp]"
```

**Open at:** `http://localhost:8008` *(separate UI — independent of localhost:3000)*

The [MCP Interaction service](https://github.com/mongodb-industry-solutions/leafy-bank-capitalmarkets-mcp) is the cleanest single-screen demonstration of **MongoDB as an AI data layer**. It spawns the [mongodb-mcp-server](https://github.com/mongodb-js/mongodb-mcp-server) as a child process and communicates with it via JSON-RPC. A ReAct agent translates natural language questions into MCP tool calls (`find`, `aggregate`, `list-collections`) and streams the full reasoning chain back to the UI in real time.

Key talking points:
- The agent has **no MongoDB driver** — it only speaks MCP protocol
- Every tool call and response is visible in the console panel — nothing is hidden
- Read-only access is **enforced at the MCP Server level**, safe for live demos against Atlas

> **Prerequisites:** Atlas programmatic API keys (`atlas_api_client_id` / `atlas_api_client_secret`) in `secrets.yml`, and AWS credentials in `~/.aws` (mounted automatically by Docker). Run `cm-loaders` at least once first to populate `yfinanceMarketData` and `binanceCryptoData`.

---

## Upstream repositories

For implementation details and the "Where Does MongoDB Shine?" narrative for each service:

| Service | Repository |
|---|---|
| UI | [leafy-bank-ui (staging)](https://github.com/mongodb-industry-solutions/leafy-bank-ui/tree/staging) |
| Accounts | [leafy-bank-backend-accounts](https://github.com/mongodb-industry-solutions/leafy-bank-backend-accounts) |
| Transactions | [leafy-bank-backend-transactions](https://github.com/mongodb-industry-solutions/leafy-bank-backend-transactions) |
| Chatbot / PDF-RAG | [cross-backend-pdf-rag](https://github.com/mongodb-industry-solutions/cross-backend-pdf-rag) |
| Open Finance | [leafy-bank-backend-openfinance](https://github.com/mongodb-industry-solutions/leafy-bank-backend-openfinance) |
| CM Loaders | [leafy-bank-backend-capitalmarkets-loaders](https://github.com/mongodb-industry-solutions/leafy-bank-backend-capitalmarkets-loaders) |
| CM Agents | [leafy-bank-backend-capitalmarkets-agents](https://github.com/mongodb-industry-solutions/leafy-bank-backend-capitalmarkets-agents) |
| CM Market Assistant | [leafy-bank-backend-capitalmarkets-react-agent-chatbot](https://github.com/mongodb-industry-solutions/leafy-bank-backend-capitalmarkets-react-agent-chatbot) |
| CM Crypto Assistant | [leafy-bank-backend-capitalmarkets-react-agent-crypto](https://github.com/mongodb-industry-solutions/leafy-bank-backend-capitalmarkets-react-agent-crypto) |
| CM MCP Interaction | [leafy-bank-capitalmarkets-mcp](https://github.com/mongodb-industry-solutions/leafy-bank-capitalmarkets-mcp) |

---

## Prerequisites

| Tool | Notes |
|------|-------|
| Ansible ≥ 2.14 | `pip install ansible-core` |
| Docker Desktop | Must be running |
| Python ≥ 3.10 | For Ansible itself |
| Git | To clone service repos |

Install the required Ansible collections once, from inside the venv:

```bash
cd leafy-bank
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ansible-galaxy collection install -r requirements.yml
```

---

## Quick Start

### 1. Configure credentials

```bash
cp vars/secrets.example.yml vars/secrets.yml
```

Edit `vars/secrets.yml` and fill in:

- `mongodb_uri` — your Atlas connection string (`mongodb+srv://user:pass@cluster.mongodb.net/`)
- `atlas_project_id` / `atlas_project_name` — from the Atlas UI
- `aws_*` — AWS credentials with Bedrock access (Capital Markets services)
- `voyage_api_key`, `tavily_api_key` — Capital Markets assistants
- `fred_api_key`, `reddit_*` — Capital Markets loaders (Reddit keys may take days to approve)
- `atlas_api_client_id` / `atlas_api_client_secret` — Atlas programmatic API keys (MCP service)

`vars/secrets.yml` is gitignored and will never be committed.

### 2. Deploy

**Always activate the venv first:**
```bash
source .venv/bin/activate
```

**Core only** (Accounts + Transactions + UI):
```bash
ansible-playbook site.yml
```

**Add the Personal Banking Assistant chatbot** (generate PDF first):
```bash
python3 scripts/generate_chatbot_pdf.py
ansible-playbook site.yml -e "extra_services=[chatbot]"
```

**Recommended for Agentic AI demos** (all Capital Markets, no chatbot):
```bash
ansible-playbook site.yml -e "deploy_services=[accounts,transactions,openfinance,cm-loaders,cm-agents,cm-market-assistant,cm-crypto-assistant,cm-mcp]"
```

**Add Open Finance to core:**
```bash
ansible-playbook site.yml -e "extra_services=[openfinance]"
```

**Custom selection:**
```bash
ansible-playbook site.yml -e "deploy_services=[accounts,transactions,openfinance]"
```

**Skip the UI** (backends only):
```bash
ansible-playbook site.yml -e "deploy_ui=false"
```

### 3. Open the demo

| URL | What's there |
|---|---|
| `http://localhost:3000` | Leafy Bank UI — main demo interface |
| `http://localhost:8008` | MCP Interaction — standalone Agentic AI demo |

---

## Teardown

**Tear down everything and start fresh:**
```bash
source .venv/bin/activate
ansible-playbook teardown.yml -e "deploy_all=true"
```

**Tear down a specific set:**
```bash
ansible-playbook teardown.yml -e "deploy_services=[cm-loaders,cm-agents]"
```

The teardown removes containers, images, and volumes but leaves the cloned repos in `services/` intact so the next deploy skips the git clone step.

---

## Service selection reference

| Service name | Port | Required keys beyond `mongodb_uri` |
|---|---|---|
| `accounts` | 8080 | — |
| `transactions` | 8001 | — |
| `chatbot` | 8002 | `aws_*` · run `generate_chatbot_pdf.py` first |
| `openfinance` | 8003 | — |
| `cm-loaders` | 8004 | `voyage_api_key`, `fred_api_key`, `reddit_*` |
| `cm-agents` | 8005 | `voyage_api_key`, `aws_*`, `bedrock_chat_model_id` |
| `cm-market-assistant` | 8006 | `voyage_api_key`, `tavily_api_key`, `aws_*` |
| `cm-crypto-assistant` | 8007 | `voyage_api_key`, `tavily_api_key`, `aws_*` |
| `cm-mcp` | 8008 | `atlas_api_client_id`, `atlas_api_client_secret`, `aws_*` |

> **Capital Markets dependency order:** `cm-loaders` → `cm-agents` → assistants.
> Run a loader cycle after deployment before querying the assistants.

---

## Repository layout

```
leafy-bank/
├── ansible.cfg                 # Ansible config (inventory, roles path, etc.)
├── inventory.yml               # localhost connection
├── requirements.yml            # Ansible collections (community.docker, community.general)
├── site.yml                    # Deploy playbook
├── teardown.yml                # Remove playbook
├── group_vars/
│   └── all.yml                 # Service definitions, ports, env var mappings
├── vars/
│   ├── secrets.example.yml     # Template — copy to secrets.yml
│   └── secrets.yml             # Your credentials (gitignored)
├── roles/
│   ├── mongodb_setup/          # Creates databases and collections before services start
│   ├── docker_service/         # Generic role: clone → patch → .env → docker compose up
│   │   ├── defaults/main.yml
│   │   ├── tasks/main.yml
│   │   └── templates/env.j2
│   └── leafy_bank_ui/          # UI role: clone (staging) → .env.local → compose up
│       ├── tasks/main.yml
│       └── templates/env.local.j2
└── services/                   # Created at runtime — cloned repos live here (gitignored)
```

---

## Customisation

### Changing ports

Edit `group_vars/all.yml` — each service entry has a `port` field. The UI's `.env.local` is regenerated from those values on every run.

### Pinning a branch

Each service entry in `group_vars/all.yml` has a `branch` field. Change it to pin to a specific release.

### Adding environment variables

Each service entry has an `env_vars` dict. Values may reference any variable in `secrets.yml` or `all.yml` using standard Jinja2 (`{{ variable_name }}`).

### Patching upstream config files

Each service entry supports a `file_patches` list for regex replacements applied after cloning. Used internally to adapt the chatbot service for local deployment. See `group_vars/all.yml` for examples.
