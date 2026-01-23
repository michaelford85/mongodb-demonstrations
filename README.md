# mongodb-demonstrations

This repository is a curated collection of **MongoDB Atlas demonstrations** that I use for learning, experimentation, customer demos, and technical storytelling. Each folder is designed to be **self-contained**, focused on a specific Atlas capability or integration pattern.

The goal of this repo is not to provide production-ready applications, but rather **clear, minimal, and explainable demos** that highlight *why* and *how* you would use specific MongoDB Atlas features.

---

## Repository Structure

Each top-level folder represents an independent demonstration:

```
mongodb-demonstrations/
├── api-examples/
├── atlas-oauth2-authentication/
├── credentials/
├── full-text-search/
├── voyageai-vector-embeddings/
└── README.md
```

Below is a brief description of what each folder contains.

---

## Folder Overview

### `api-examples/`

Demonstrations focused on interacting with MongoDB Atlas and MongoDB data using APIs and SDKs.

Typical examples may include:

- Basic CRUD operations via drivers
- REST-style service patterns backed by MongoDB
- Lightweight FastAPI or Flask examples
- Atlas Admin API usage

---

### `atlas-oauth2-authentication/`

Examples showing how to authenticate to MongoDB Atlas using **OAuth 2.0** instead of traditional username/password credentials.

This folder is intended to demonstrate:

- Federated authentication concepts
- Integration with external identity providers (IdPs)
- Token-based authentication flows
- Secure, enterprise-friendly access patterns

---

### `credentials/`

Patterns and examples for **secure credential handling** when working with MongoDB Atlas.

This may include:

- Environment-variable based configuration
- `.env` file usage
- Secret management patterns
- Clear examples of what *not* to commit to source control

---

### `full-text-search/`

Demonstrations of **MongoDB Atlas Search**, including full-text and relevance-based querying.

Typical scenarios include:

- Text search with scoring
- Filters and facets
- Synonyms and analyzers
- Search vs. traditional query comparisons

---

### `voyageai-vector-embeddings/`

Examples focused on **vector embeddings and semantic search** using MongoDB Atlas Vector Search.

This folder highlights:

- Generating embeddings with VoyageAI
- Storing and indexing vector data in Atlas
- Performing semantic and hybrid search
- Foundations for RAG-style applications

---

## Python Dependencies

Each demonstration folder will include its **own ****requirements.txt**** file**.

This is intentional and by design:

- Each demo is self-contained
- Dependencies are explicit and minimal
- You can run or demo folders independently
- No global dependency coupling across demos

Example:

```
cd full-text-search
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Notes

- These demos are intentionally lightweight and focused
- Code favors clarity over cleverness
- Expect this repository to grow over time as new Atlas features and integrations are added

If you are browsing this repo for learning or demo inspiration, feel free to start with whichever folder aligns best with your use case.

More detailed documentation lives **inside each folder**.

