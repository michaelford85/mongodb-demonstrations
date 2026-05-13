# VoyageAI + MongoDB Atlas — E-Commerce Search Demo

A Streamlit app that tells the story of how AI-native search transforms product discovery.
Four search strategies run side-by-side so you can see exactly where each one wins.

| Tab | Strategy | What it shows |
|-----|----------|---------------|
| 🔤 Keyword | Atlas Search BM25 | The baseline — fast, but misses intent |
| 🧠 Semantic | VoyageAI `voyage-3.5` embeddings | Finds meaning, not just words |
| ⚡ Hybrid | Semantic + keyword via RRF | Precision and understanding combined |
| 🎯 + Rerank | Hybrid + VoyageAI `voyage-rerank-2` | Best match always surfaces first |

---

## Prerequisites

- Python 3.11+
- MongoDB Atlas cluster (M10 or larger) with Atlas Search enabled
- VoyageAI API key — [voyageai.com](https://www.voyageai.com)
- Hugging Face account (free) for the Amazon dataset download

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your MongoDB URI, cert path, and VoyageAI API key
```

### 3. Load product data (~15k products across 3 categories)

```bash
python scripts/load_data.py --limit 5000
```

> The first run downloads the Amazon dataset from Hugging Face (~500 MB).
> Subsequent runs are instant. Use `--drop` to reload from scratch.

### 4. Create Atlas Search indexes

```bash
python scripts/create_indexes.py
```

Atlas builds indexes asynchronously. **Wait 1–2 minutes** before proceeding.
You can monitor progress in the Atlas UI under **Search Indexes**.

### 5. Add VoyageAI embeddings

```bash
python scripts/add_embeddings.py
```

This embeds ~15k products using `voyage-3.5`. With BATCH_SIZE=128 and standard
VoyageAI rate limits, expect 15–30 minutes. Safe to interrupt and re-run —
it only processes documents missing an `embedding` field.

### 6. Run the demo

```bash
streamlit run app.py
```

---

## Good demo queries

These queries are pre-loaded in the app dropdown and designed to highlight
the progression from keyword → semantic → hybrid → rerank:

- `comfortable shoes for walking and standing all day` — keyword fails, semantic wins
- `gift for someone who loves cooking` — keyword gets nothing, semantic shines
- `laptop that won't die on a long flight` — semantic captures battery/travel intent
- `noise cancelling headphones for a noisy open office` — hybrid beats both
- `home office setup for video calls` — multi-product intent query
- `something to help me sleep better` — reranker dramatically improves ordering
- `waterproof jacket for hiking in the rain` — semantic + hybrid parity
- `affordable robot vacuum for pet hair` — hybrid + rerank best

---

## Architecture

```
Amazon Products (HuggingFace)
    ↓ scripts/load_data.py
MongoDB Atlas (ecommerce_demo.products)
    ↓ scripts/create_indexes.py
    ├── product_vector_index  (Atlas Vector Search, cosine, 1024d)
    └── product_text_index   (Atlas Search, BM25, english analyzer)
    ↓ scripts/add_embeddings.py
    └── embedding field  (VoyageAI voyage-3.5, input_type=document)

Streamlit app.py
    ├── search/keyword.py   → $search (BM25)
    ├── search/semantic.py  → $vectorSearch + voyage-3.5 query embed
    ├── search/hybrid.py    → $vectorSearch + $unionWith($search) + RRF
    └── search/rerank.py    → hybrid results → voyage-rerank-2
```

---

## Notes

- **Auto-embeddings**: Once MongoDB Atlas auto-embeddings reaches GA, the
  `scripts/add_embeddings.py` step and the `embedding` field management can
  be replaced by an Atlas trigger. The search queries remain unchanged.
- **Image URLs**: Product images come from the Amazon dataset and may occasionally
  be stale. The app falls back to a placeholder gracefully.
- **Cost**: Embedding 15k products uses ~3M tokens on VoyageAI. Each demo search
  (semantic + hybrid + rerank) uses ~1k tokens. Both are well within free tier limits.
