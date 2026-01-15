# MongoDB Atlas Search vs. Regex: A Comparison

This project demonstrates why **MongoDB Atlas Search** (powered by Apache Lucene) is superior to standard **regex** for full‑text search use cases. Using the `sample_mflix` dataset, we compare performance, relevance, and functionality.

---

## 🚀 The Core Benefits

### 1) Performance at Scale
Regex typically requires a collection scan (or an index scan that still evaluates many candidates), which slows down as your collection grows. Atlas Search uses an **inverted index**, enabling fast lookups even at large scale.

### 2) Relevance Scoring
Regex is a simple match/no‑match filter. Atlas Search computes a **relevance score** so the best matches appear first (e.g., Lucene scoring, BM25-style relevance).

### 3) Linguistic Intelligence (Fuzzy Matching)
Regex is literal—typos and variations usually fail. Atlas Search supports **fuzzy matching**, analyzers, tokenization, and more, so it can return relevant results even with imperfect queries.

---

## 🛠 Project Setup

### Prerequisites
- A MongoDB Atlas cluster with the **`sample_mflix`** dataset loaded
- Python 3.x
- `pymongo`

Install Python dependencies:
```bash
pip install pymongo
```

---

## 🔐 Environment Variables (.env)

This project reads configuration from a local `.env` file.

### Required values
Create a file named **`.env`** in the project root with:

```env
# Atlas Search index name (on sample_mflix.movies)
FTS_INDEX_NAME=movies_title_index

# sample_mflix defaults (Option 1)
DB_NAME=sample_mflix
COLLECTION_NAME=movies

# Your Atlas connection string (must have access to sample_mflix)
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-host>/?retryWrites=true&w=majority
```

> Notes:
> - `DB_NAME` should be `sample_mflix`
> - `COLLECTION_NAME` should be `movies`
> - `MONGODB_URI` must point to your Atlas cluster (and credentials must have read access to `sample_mflix`).

---

## 🔒 dotenv-vault (Recommended)

This repo supports **dotenv-vault** so you can share environment variables securely without committing `.env`.

### Option A — Use a Shared Vault (recommended for teams/workshops)
1) Export your `DOTENV_KEY` (you’ll be given this value):
```bash
export DOTENV_KEY=<your_dotenv_key>
```

2) Pull the `.env` file:
```bash
npx dotenv-vault@latest pull
```

That will create/update your local `.env`.

### Option B — Create Your Own Vault (if you prefer)
1) Create a vault for this repo:
```bash
npx dotenv-vault@latest new regex_fts_comparison
```

2) Create your `.env` locally (see the required values above), then push:
```bash
npx dotenv-vault@latest push
```

3) On any machine where you want to pull secrets:
```bash
export DOTENV_KEY=<your_dotenv_key>
npx dotenv-vault@latest pull
```

---

## 🔎 The Search Index

The script automatically handles creation of a **static Atlas Search index** on the `title` field. By using static mapping instead of dynamic mapping, you can reduce index size and improve performance.

**Index Definition**
```json
{
  "mappings": {
    "dynamic": false,
    "fields": {
      "title": {
        "type": "string",
        "analyzer": "lucene.standard"
      }
    }
  }
}
```

---

## ▶️ Run the Comparison

Once your `.env` is set:

```bash
python regex_fts_comparison.py
```

The script will:
- Connect to `sample_mflix.movies`
- Ensure the Atlas Search index exists (if applicable)
- Run comparable queries using:
  - Atlas Search ($search)
  - Regex ($regex)
- Print/compare results (timing + relevance characteristics)

---

## ✅ Security / Git Hygiene

Do **not** commit secrets. Ensure `.env` is ignored:

```gitignore
.env
```

dotenv-vault replaces committed secrets with a secure vault workflow.

---

## License
MIT (or update if you use something else)
