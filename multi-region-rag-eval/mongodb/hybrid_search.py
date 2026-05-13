"""Hybrid (BM25 + vector) search on Atlas, with optional Voyage reranking.

Vector search alone retrieves semantically similar documents but can
under-weight rare lexical anchors (e.g. account-suffix digits) when a
cluster of near-duplicate names is present. Lucene BM25 alone handles
exact lexical anchors well but misses paraphrases. The two arms cover
each other's failure modes; reciprocal rank fusion (RRF) merges them
into a single ranking without needing either score to be calibrated
against the other.

This script prints the vector-only top-k and the hybrid (RRF) top-k for
the same query side-by-side, which is the relevance lift the demo is
intended to showcase. Pass ``--rerank`` to add a Voyage cross-encoder
re-scoring stage on top of the hybrid candidate pool.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from pymongo import MongoClient
from tabulate import tabulate

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import load_settings  # noqa: E402
from embeddings import embed_account  # noqa: E402
from rerankers import rerank as voyage_rerank  # noqa: E402

RRF_K = 60  # Standard reciprocal-rank-fusion damping constant.


def _bm25_pipeline(query: str, region: str | None, k: int, index_name: str) -> list[dict]:
    text_op = {
        "query": query,
        "path": "account_name",
        "fuzzy": {"maxEdits": 2, "prefixLength": 1},
    }
    if region:
        # `region` is indexed as a `token` field, so `equals` (not `text`)
        # is the operator that matches against the verbatim token.
        search_stage: dict[str, Any] = {"$search": {
            "index": index_name,
            "compound": {
                "must": [{"text": text_op}],
                "filter": [{"equals": {"path": "region", "value": region}}],
            },
        }}
    else:
        search_stage = {"$search": {"index": index_name, "text": text_op}}
    return [
        search_stage,
        {"$limit": k},
        {"$project": {
            "_id": 0,
            "account_name": 1, "product_group": 1, "region": 1,
            "sales_area": 1, "service_agent_id": 1, "operational_identity": 1,
            "bm25_score": {"$meta": "searchScore"},
        }},
    ]


def _vector_pipeline(
    query_vec: list[float], region: str | None, k: int, index_name: str,
) -> list[dict]:
    stage: dict[str, Any] = {"$vectorSearch": {
        "index": index_name,
        "path": "embedding",
        "queryVector": query_vec,
        "numCandidates": max(100, k * 20),
        "limit": k,
    }}
    if region:
        stage["$vectorSearch"]["filter"] = {"region": {"$eq": region}}
    return [
        stage,
        {"$project": {
            "_id": 0,
            "account_name": 1, "product_group": 1, "region": 1,
            "sales_area": 1, "service_agent_id": 1, "operational_identity": 1,
            "vector_score": {"$meta": "vectorSearchScore"},
        }},
    ]


def _rrf_merge(bm25: list[dict], vec: list[dict], k_const: int = RRF_K) -> list[dict]:
    """Reciprocal rank fusion: score(d) = sum_r 1 / (k + rank_r(d)).

    Documents are de-duplicated by ``account_name`` (unique per row in the
    synthetic dataset). The merged dict carries both per-arm scores plus
    a ``fused_score`` for sorting; per-arm scores from each ranker are
    merged in rather than only kept from whichever ranker saw the doc
    first.
    """
    scored: dict[str, float] = {}
    seen: dict[str, dict] = {}
    for ranker in (bm25, vec):
        for rank, doc in enumerate(ranker, start=1):
            key = doc["account_name"]
            scored[key] = scored.get(key, 0.0) + 1.0 / (k_const + rank)
            if key in seen:
                # Carry forward per-arm score fields from this ranker that
                # the first ranker didn't have (e.g. vector_score when the
                # doc was first seen by the BM25 arm).
                for k, v in doc.items():
                    if k not in seen[key] or seen[key][k] is None:
                        seen[key][k] = v
            else:
                seen[key] = dict(doc)
    out: list[dict] = []
    for key, score in sorted(scored.items(), key=lambda kv: -kv[1]):
        merged = dict(seen[key])
        merged["fused_score"] = score
        out.append(merged)
    return out


def _run_pipeline(coll, pipeline: list[dict]) -> tuple[list[dict], float]:
    start = time.perf_counter()
    rows = list(coll.aggregate(pipeline))
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return rows, elapsed_ms


def _format_rows(rows: list[dict], score_keys: list[str]) -> list[list]:
    out = []
    for r in rows:
        scores = [f"{r.get(k, 0.0):.4f}" if r.get(k) is not None else "" for k in score_keys]
        out.append([
            *scores,
            r["account_name"], r["region"], r["product_group"],
            r["sales_area"], r["service_agent_id"],
        ])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True,
                        help="Misspelled or partial account_name from the inbound email.")
    parser.add_argument("--product", default="Software")
    parser.add_argument("--region", default=None,
                        help="Pre-filter region; omit for global search.")
    parser.add_argument("-k", type=int, default=5,
                        help="Final number of rows to display (default: 5).")
    parser.add_argument(
        "--candidates", type=int, default=25,
        help="Candidates fetched per arm (vector and BM25) before RRF fusion "
             "(default: 25).",
    )
    parser.add_argument(
        "--rerank", action="store_true",
        help="Apply Voyage rerank to the fused candidate pool.",
    )
    args = parser.parse_args()

    settings = load_settings()

    with MongoClient(settings.mongo_uri) as client:
        coll = client[settings.mongo_db][settings.mongo_collection]

        # Untimed warm-up against both indexes.
        warm_vec = embed_account(
            "__warmup__", args.product, settings.voyage_api_key,
            settings.voyage_model, settings.embed_dim,
        )
        _run_pipeline(coll, _vector_pipeline(
            warm_vec, args.region, args.candidates, settings.atlas_vector_index,
        ))
        _run_pipeline(coll, _bm25_pipeline(
            "__warmup__", args.region, args.candidates, settings.atlas_search_index,
        ))

        query_vec = embed_account(
            args.query, args.product, settings.voyage_api_key,
            settings.voyage_model, settings.embed_dim,
        )
        vec_rows, vec_ms = _run_pipeline(coll, _vector_pipeline(
            query_vec, args.region, args.candidates, settings.atlas_vector_index,
        ))
        bm25_rows, bm25_ms = _run_pipeline(coll, _bm25_pipeline(
            args.query, args.region, args.candidates, settings.atlas_search_index,
        ))

    fused = _rrf_merge(bm25_rows, vec_rows)

    rerank_ms = 0.0
    reranked: list[dict] = []
    if args.rerank:
        reranked, rerank_ms = voyage_rerank(
            args.query, fused[: args.candidates],
            api_key=settings.voyage_api_key,
            model=settings.voyage_rerank_model,
            top_k=args.k,
        )

    print(f"\nIncoming query: {args.query!r}  product={args.product}  "
          f"region={args.region or 'ALL'}  k={args.k}  candidates={args.candidates}")
    print(f"vector latency: {vec_ms:7.1f} ms  |  "
          f"BM25 latency: {bm25_ms:7.1f} ms"
          + (f"  |  rerank latency: {rerank_ms:7.1f} ms" if args.rerank else ""))
    print()

    print("Vector-only top-k:")
    print(tabulate(
        _format_rows(vec_rows[: args.k], ["vector_score"]),
        headers=["vector", "account_name", "region", "product_group",
                 "sales_area", "agent_id"],
        tablefmt="github",
    ))

    print("\nHybrid (BM25 + vector, RRF) top-k:")
    print(tabulate(
        _format_rows(fused[: args.k], ["fused_score", "bm25_score", "vector_score"]),
        headers=["fused", "bm25", "vector", "account_name", "region",
                 "product_group", "sales_area", "agent_id"],
        tablefmt="github",
    ))

    if args.rerank:
        print("\nHybrid + Voyage rerank top-k:")
        print(tabulate(
            _format_rows(reranked, ["rerank_score", "fused_score"]),
            headers=["rerank", "fused", "account_name", "region",
                     "product_group", "sales_area", "agent_id"],
            tablefmt="github",
        ))


if __name__ == "__main__":
    main()
