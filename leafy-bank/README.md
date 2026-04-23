# Leafy Bank — Ansible Automation

Ansible playbooks for deploying the [Leafy Bank](https://github.com/mongodb-industry-solutions/leafy-bank-ui) demo application locally using Docker. Leafy Bank is a MongoDB Financial Services reference implementation: a Next.js frontend backed by a constellation of Python microservices that showcase Atlas features like multi-document ACID transactions, Vector Search, Time Series collections, and agentic AI workflows.

Rather than cloning nine repositories and hand-crafting `.env` files, this automation:

- Clones each selected backend service repo and the UI.
- Generates a correctly wired `.env` / `.env.local` from a single secrets file.
- Builds and starts every container via Docker Compose.

---

## Architecture

```
Leafy Bank UI  (Next.js, port 3000)
├── Accounts Service           port 8080  [core]
├── Transactions Service        port 8001  [core]
├── Chatbot / PDF-RAG           port 8002  [optional]
├── Open Finance Service        port 8003  [optional]
├── Capital Markets — Loaders   port 8004  [optional]
├── Capital Markets — Agents    port 8005  [optional]
├── Capital Markets — Market Assistant  port 8006  [optional]
└── Capital Markets — Crypto Assistant  port 8007  [optional]
```

All services connect to your existing **MongoDB Atlas** cluster.

---

## Demo Walkthrough

Leafy Bank is structured as three progressive tiers. Each tier introduces new MongoDB capabilities on top of the last. Deploy only what you need for a given conversation.

---

### Tier 1 — Core Banking (Accounts + Transactions)

**Deploy:** `ansible-playbook site.yml`

Select any demo user from the welcome screen, then explore:

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

### Tier 2 — Open Finance + AI Assistant

**Deploy:** `ansible-playbook site.yml -e "extra_services=[chatbot,openfinance]"`

- **Open Finance** — connect to simulated external institutions. The service aggregates accounts and products (loans, mortgages) from multiple sources into a unified financial summary. Demonstrates **aggregation pipelines** combining heterogeneous data and MongoDB's **BSON/JSON compatibility** with external APIs — no serialisation layer needed.
- **Leafy Personal Assistant** — a chatbot that answers questions about banking terms, conditions, and account details. Backed by **Atlas Vector Search**: PDF documents are chunked, embedded, and stored as vectors in MongoDB. User questions are embedded at query time and matched semantically — not by keyword — against the stored chunks.

**MongoDB capabilities on show:**
| Capability | Where you see it |
|---|---|
| Aggregation pipelines | Global financial summary across internal + external accounts |
| Atlas Vector Search | Chatbot semantic retrieval over PDF content |
| Flexible schema | Heterogeneous external account/product documents in one collection |

---

### Tier 3 — Capital Markets & Agentic AI

**Deploy:** `ansible-playbook site.yml -e "deploy_all=true"`

> **Important:** `cm-loaders` must run and complete a data load cycle before the agents and assistants have data to work with. Trigger a load via the UI or the loaders API after deployment.

- **Market & Crypto portfolios** — view pre-built investment portfolios for traditional assets (stocks, ETFs) and cryptocurrency. Data is ingested from Yahoo Finance, Binance, FRED, and CoinGecko via the loaders service and stored in **Time Series collections** — optimised storage and querying for high-frequency market data.
- **Scheduled Agents** — six specialised AI agents run on a schedule, each analysing a different signal: price trends, financial news sentiment, and social media sentiment for both traditional and crypto assets. Agent reports are stored in MongoDB and retrieved via **Atlas Vector Search** using the `voyage-finance-2` finance-domain embedding model.
- **Market Assistant & Crypto Assistant** — ReAct (Reason and Act) conversational agents built with LangGraph. Ask natural language questions about portfolios, market conditions, or asset allocation. These agents showcase two Atlas capabilities working together:
  - **Atlas Vector Search** — semantic retrieval of agent-generated reports
  - **MongoDB as agent memory** — the LangGraph checkpointer persists the full agent state (reasoning steps, tool calls, intermediate results) into MongoDB collections after every interaction step, enabling true multi-turn conversations with full context

**MongoDB capabilities on show:**
| Capability | Where you see it |
|---|---|
| Time Series collections | Market and crypto price history (yfinance, Binance) |
| Atlas Vector Search | Agent report retrieval with finance-domain embeddings |
| Agentic AI memory | LangGraph checkpointer stores agent state in MongoDB |
| Document model for agent state | Complex nested agent state maps naturally to BSON |
| Scheduled writes | Loaders and agent report generation run on a timer |

---

## Upstream repositories

For implementation details and the "Where Does MongoDB Shine?" narrative for each service:

| Service | Repository |
|---|---|
| UI | [leafy-bank-ui (staging)](https://github.com/mongodb-industry-solutions/leafy-bank-ui/tree/staging) |
| Accounts | [leafy-bank-backend-accounts](https://github.com/mongodb-industry-solutions/leafy-bank-backend-accounts) |
| Transactions | [leafy-bank-backend-transactions](https://github.com/mongodb-industry-solutions/leafy-bank-backend-transactions) |
| Chatbot | [cross-backend-pdf-rag](https://github.com/mongodb-industry-solutions/cross-backend-pdf-rag) |
| Open Finance | [leafy-bank-backend-openfinance](https://github.com/mongodb-industry-solutions/leafy-bank-backend-openfinance) |
| CM Loaders | [leafy-bank-backend-capitalmarkets-loaders](https://github.com/mongodb-industry-solutions/leafy-bank-backend-capitalmarkets-loaders) |
| CM Agents | [leafy-bank-backend-capitalmarkets-agents](https://github.com/mongodb-industry-solutions/leafy-bank-backend-capitalmarkets-agents) |
| CM Market Assistant | [leafy-bank-backend-capitalmarkets-react-agent-chatbot](https://github.com/mongodb-industry-solutions/leafy-bank-backend-capitalmarkets-react-agent-chatbot) |
| CM Crypto Assistant | [leafy-bank-backend-capitalmarkets-react-agent-crypto](https://github.com/mongodb-industry-solutions/leafy-bank-backend-capitalmarkets-react-agent-crypto) |

---

## Prerequisites

| Tool | Notes |
|------|-------|
| Ansible ≥ 2.14 | `pip install ansible-core` |
| Docker Desktop | Must be running |
| Python ≥ 3.10 | For Ansible itself |
| Git | To clone service repos |

Install the required Ansible collection once:

```bash
python3 -m venv .venv
source .venv/bin/activate
ansible-galaxy collection install -r requirements.yml
```

---

## Quick Start

### 1. Configure credentials

```bash
cp vars/secrets.example.yml vars/secrets.yml
```

Edit `vars/secrets.yml` and fill in:

- `mongodb_uri` — your Atlas connection string
- `atlas_project_id` / `atlas_project_name` — from the Atlas UI
- AWS credentials (needed for chatbot and all Capital Markets services)
- API keys for VoyageAI, Tavily, FRED, and Reddit (Capital Markets only)

`vars/secrets.yml` is gitignored and will never be committed.

### 2. Deploy

**Core only** (Accounts + Transactions + UI):

```bash
ansible-playbook site.yml
```

**Add optional services:**

```bash
ansible-playbook site.yml -e "extra_services=[chatbot,openfinance]"
```

**Deploy everything:**

```bash
ansible-playbook site.yml -e "deploy_all=true"
```

**Custom selection** (overrides all defaults):

```bash
ansible-playbook site.yml -e "deploy_services=[accounts,transactions,chatbot]"
```

**Skip the UI** (backends only):

```bash
ansible-playbook site.yml -e "deploy_ui=false"
```

### 3. Open the demo

```
http://localhost:3000
```

---

## Service selection reference

| Service name | Port | Required keys beyond `mongodb_uri` |
|---|---|---|
| `accounts` | 8080 | — |
| `transactions` | 8001 | — |
| `chatbot` | 8002 | `aws_*`, `chatbot_*_model` |
| `openfinance` | 8003 | — |
| `cm-loaders` | 8004 | `voyage_api_key`, `fred_api_key`, `reddit_*` |
| `cm-agents` | 8005 | `voyage_api_key`, `aws_*`, `bedrock_chat_model_id` |
| `cm-market-assistant` | 8006 | `voyage_api_key`, `tavily_api_key`, `aws_*` |
| `cm-crypto-assistant` | 8007 | `voyage_api_key`, `tavily_api_key`, `aws_*` |

> **Capital Markets dependency order:** `cm-loaders` must run first to populate collections before `cm-agents` can generate reports, and the assistant services (`cm-market-assistant`, `cm-crypto-assistant`) depend on those reports.

---

## Teardown

Stop and remove all containers, images, and volumes for the default service set:

```bash
ansible-playbook teardown.yml
```

Use the same `-e` flags as `site.yml` to target a subset.

---

## Repository layout

```
leafy-bank/
├── ansible.cfg                 # Ansible config (inventory, roles path, etc.)
├── inventory.yml               # localhost connection
├── requirements.yml            # community.docker collection
├── site.yml                    # Deploy playbook
├── teardown.yml                # Remove playbook
├── group_vars/
│   └── all.yml                 # Service definitions, ports, env var mappings
├── vars/
│   ├── secrets.example.yml     # Template — copy to secrets.yml
│   └── secrets.yml             # Your credentials (gitignored)
├── roles/
│   ├── docker_service/         # Generic role: clone → .env → docker compose up
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

---

