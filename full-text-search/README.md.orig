# MongoDB Atlas Search vs. Regex: A Comparison

This project demonstrates why **MongoDB Atlas Search** (powered by Apache Lucene) is superior to standard **Regex** for full-text search use cases. Using the `sample_mflix` dataset, we compare performance, relevance, and functionality.

## 🚀 The Core Benefits

### 1. Performance at Scale
Regex requires a "linear" scan or a B-tree index scan, which slows down as your collection grows. Atlas Search uses an **Inverted Index**, providing sub-second results even on massive datasets.



### 2. Relevance Scoring
Regex treats matches as a simple "True/False" boolean. Atlas Search assigns a **Score** to every document based on algorithms like **TF-IDF** (Term Frequency-Inverse Document Frequency), ensuring the most relevant results appear first.

### 3. Linguistic Intelligence (Fuzzy Matching)
Regex is literal; if there is a typo, it fails. Atlas Search supports **Fuzzy Search**, allowing it to find "Black Cat" even if the user types "Blck Cat".

## 🛠 Project Setup

### Prerequisites
* A MongoDB Atlas cluster with the `sample_mflix` dataset loaded.
* Python 3.x installed.
* `pymongo` library installed: `pip install pymongo`.

### The Search Index
The script automatically handles the creation of a **Static Index** on the `title` field. By using static mapping instead of dynamic, we reduce index size and improve performance.

**Index Definition:**
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