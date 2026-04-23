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

## Prerequisites

| Tool | Notes |
|------|-------|
| Ansible ≥ 2.14 | `pip install ansible` |
| Docker Desktop | Must be running |
| Python ≥ 3.10 | For Ansible itself |
| Git | To clone service repos |

Install the required Ansible collection once:

```bash
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

## Upstream repositories

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
