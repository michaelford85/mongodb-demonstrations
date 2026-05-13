# MongoDB Demonstrations

A growing collection of self-contained demos for **MongoDB Atlas** — covering provisioning, replication and sharding, search and vector search, encryption, change streams, retrieval-augmented generation, agentic AI, and several head-to-head comparisons against other cloud databases.

Each subfolder is independent and ships with its own README, `.env.example`, dependencies, and run instructions. Pick the topic you're interested in and start there.

## Prerequisites

Most demos connect to a running Atlas cluster. Two folders exist to provision one declaratively via Terraform — start with these if you don't already have a cluster handy:

| Folder | Purpose |
|---|---|
| **[`atlas-cluster-provisioning/`](./atlas-cluster-provisioning/)** | Dedicated replica-set cluster (single- or multi-region), with optional Atlas Search nodes and Compute Auto-Scale enabled by default (the prerequisite for Atlas Automated Embedding). |
| **[`atlas-sharded-cluster-provisioning/`](./atlas-sharded-cluster-provisioning/)** | Companion module for `SHARDED` and `GEOSHARDED` (Global Cluster) topologies with per-shard region control. |

Each provisioner has its own `.env.example`, a one-line `./deploy.sh`, and a matching `./teardown.sh`. Demos that need other infrastructure — Azure Cosmos DB, Aurora PostgreSQL with pgvector, and others — carry their own provisioning folder alongside the demo that uses it.

## Using a demo

```bash
cd <demo-folder>            # any folder in this repo
cat README.md               # walkthrough, setup, and run order
cp .env.example .env        # fill in connection details
# then follow the folder's README for installs and run commands
```

## Conventions

- **Python** demos use [PyMongo](https://pymongo.readthedocs.io/) and [`python-dotenv`](https://pypi.org/project/python-dotenv/); `.env` is the single source of truth for connection strings and credentials.
- **Sharding** scripts are written in [`mongosh`](https://www.mongodb.com/docs/mongodb-shell/) where the shell's helpers are idiomatic (`sh.shardCollection`, `sh.updateZoneKeyRange`, and friends).
- **Infrastructure** is Terraform where the target cloud has a provider; Bicep for Azure-only resources; Ansible for orchestration of multi-service local deployments.
- Secrets stay out of git: every folder's `.gitignore` excludes `.env`, and `.env.example` files contain placeholders only.

## Who this is for

Solutions architects validating a design, developers prototyping an integration, customers evaluating a feature, or anyone curious about how Atlas behaves in practice rather than only on paper. Where a demo compares Atlas to another platform (PostgreSQL + pgvector, Cosmos DB, and others), the comparison is set up symmetrically so the trade-offs are visible from real runs.
