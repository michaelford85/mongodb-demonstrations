"""Side-by-side product-description match against both backends.

Embeds a free-text product description with Voyage AI, then runs an
identical top-k vector search on Cosmos and Atlas. The two ranked lists
are printed in adjacent blocks so the rank/score/metadata can be
eyeballed side by side, and the per-backend wall-clock round-trip is
included so the latency difference is visible without a separate tool.

The --category filter is pushed into the $vectorSearch.filter on Atlas
(pre-filter against the indexed 'category' field) and applied as a
WHERE clause on Cosmos. The metadata fields surfaced come from the
catalog schema: item_id, vendor, category, title, page_number.

Usage:
    python -m compare.product_match "portable power supply 12V industrial grade"
    python -m compare.product_match "safety data sheet flammable solvent" --category compliance --k 3
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from azure.cosmos import CosmosClient
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Settings, load_settings  # noqa: E402
from embeddings import embed_query  # noqa: E402


@dataclass
class Hit:
    rank: int
    score: float
    item_id: str
    vendor: str
    category: str
    title: str
    page_number: int
    text: str


def _snippet(text: str, width: int = 120) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= width else flat[: width - 1] + "\u2026"


def _atlas_search(coll, index_name: str, vector: list[float], k: int,
                  category: str | None) -> tuple[list[Hit], float]:
    stage: dict = {
        "$vectorSearch": {
            "index": index_name, "path": "embedding",
            "queryVector": vector, "numCandidates": max(k * 20, 100), "limit": k,
        }
    }
    if category:
        stage["$vectorSearch"]["filter"] = {"category": {"$eq": category}}
    pipeline = [
        stage,
        {"$project": {
            "_id": 0, "item_id": 1, "vendor": 1, "category": 1,
            "title": 1, "page_number": 1, "text": 1,
            "score": {"$meta": "vectorSearchScore"},
        }},
    ]
    started = time.perf_counter()
    docs = list(coll.aggregate(pipeline))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    hits = [
        Hit(rank=i + 1, score=float(d.get("score", 0.0)),
            item_id=d.get("item_id", ""), vendor=d.get("vendor", ""),
            category=d.get("category", ""), title=d.get("title", ""),
            page_number=int(d.get("page_number", 0)), text=d.get("text", ""))
        for i, d in enumerate(docs)
    ]
    return hits, elapsed_ms


def _cosmos_search(container, vector: list[float], k: int,
                   category: str | None) -> tuple[list[Hit], float]:
    where = "WHERE c.category = @cat " if category else ""
    query = (
        "SELECT TOP @k c.item_id, c.vendor, c.category, c.title, "
        "c.page_number, c.text, "
        "VectorDistance(c.embedding, @vec) AS score "
        f"FROM c {where}"
        "ORDER BY VectorDistance(c.embedding, @vec)"
    )
    parameters = [
        {"name": "@k", "value": k},
        {"name": "@vec", "value": vector},
    ]
    if category:
        parameters.append({"name": "@cat", "value": category})
    started = time.perf_counter()
    docs = list(container.query_items(
        query=query, parameters=parameters, enable_cross_partition_query=True,
    ))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    hits = [
        Hit(rank=i + 1, score=float(d.get("score", 0.0)),
            item_id=d.get("item_id", ""), vendor=d.get("vendor", ""),
            category=d.get("category", ""), title=d.get("title", ""),
            page_number=int(d.get("page_number", 0)), text=d.get("text", ""))
        for i, d in enumerate(docs)
    ]
    return hits, elapsed_ms


def _print_block(backend: str, hits: list[Hit], elapsed_ms: float) -> None:
    print(f"=== {backend.upper()}  (round-trip {elapsed_ms:.1f} ms, {len(hits)} hits) ===")
    if not hits:
        print("  (no results)")
        return
    for h in hits:
        print(
            f"  #{h.rank}  score={h.score:.4f}  {h.item_id:<16} "
            f"{h.vendor:<22} {h.category:<22} p.{h.page_number}"
        )
        print(f"        title  : {h.title}")
        print(f"        snippet: {_snippet(h.text)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Free-text product description to match.")
    parser.add_argument("--category", help="Optional category pre-filter "
                        "(pushed into $vectorSearch on Atlas, WHERE clause on Cosmos).")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--only", choices=("cosmos", "atlas", "both"), default="both")
    args = parser.parse_args()

    settings: Settings = load_settings()
    print(f"Embedding query with {settings.voyage_model} ({settings.embed_dim}d)...")
    qvec = embed_query(args.query, settings.voyage_api_key,
                       settings.voyage_model, settings.embed_dim)

    if args.only in ("atlas", "both"):
        client = MongoClient(settings.mongo_uri)
        coll = client[settings.mongo_db][settings.mongo_collection]
        hits, ms = _atlas_search(coll, settings.atlas_vector_index,
                                 qvec, args.k, args.category)
        _print_block("atlas", hits, ms)
        print()

    if args.only in ("cosmos", "both"):
        cosmos = CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
        container = (cosmos.get_database_client(settings.cosmos_database)
                     .get_container_client(settings.cosmos_container))
        hits, ms = _cosmos_search(container, qvec, args.k, args.category)
        _print_block("cosmos", hits, ms)


if __name__ == "__main__":
    main()
