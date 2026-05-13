"""Server-side hybrid search on Atlas using ``$rankFusion`` (MongoDB 8.1+).

The companion ``hybrid_search.py`` script fetches the BM25 and vector
candidate lists in two separate ``aggregate`` calls and fuses them in
Python. This script does the same hybrid in one round-trip by handing
both sub-pipelines to Atlas's native ``$rankFusion`` aggregation stage,
which executes them server-side and returns a single fused ranking with
optional per-pipeline weights and a ``scoreDetails`` breakdown.

``$rankFusion`` is a Preview feature; the cluster must run MongoDB 8.1
or higher and both the vector and Lucene indexes must already be
queryable (see ``mongodb/create_index.py``).
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


def _vector_inner(
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
    return [stage]


def _bm25_inner(
    query: str, region: str | None, k: int, index_name: str,
) -> list[dict]:
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
    return [search_stage, {"$limit": k}]


def _build_pipeline(
    *,
    query_vec: list[float],
    query: str,
    region: str | None,
    candidates: int,
    final_k: int,
    vector_index: str,
    search_index: str,
    weight_vector: float,
    weight_bm25: float,
    score_details: bool,
) -> list[dict]:
    rank_fusion: dict[str, Any] = {
        "input": {
            "pipelines": {
                "vectorPipeline": _vector_inner(
                    query_vec, region, candidates, vector_index,
                ),
                "bm25Pipeline": _bm25_inner(
                    query, region, candidates, search_index,
                ),
            },
        },
        "combination": {
            "weights": {
                "vectorPipeline": weight_vector,
                "bm25Pipeline": weight_bm25,
            },
        },
        "scoreDetails": score_details,
    }
    pipeline: list[dict] = [{"$rankFusion": rank_fusion}]
    if score_details:
        pipeline.append({"$addFields": {
            "fused_score": {"$meta": "score"},
            "scoreDetails": {"$meta": "searchScoreDetails"},
        }})
    else:
        pipeline.append({"$addFields": {"fused_score": {"$meta": "score"}}})
    pipeline.append({"$limit": final_k})
    # Exclusion projection — keeps every field except the ones listed
    # (notably the 1024-float embedding). Inclusion projections would
    # silently drop ``scoreDetails`` if ``$meta`` returned MISSING for a
    # document, which makes the missing-metadata case hard to diagnose.
    pipeline.append({"$project": {"_id": 0, "embedding": 0}})
    return pipeline


def _format_rows(rows: list[dict], with_rerank: bool) -> list[list]:
    out = []
    for r in rows:
        row = [f"{r.get('fused_score', 0.0):.4f}"]
        if with_rerank:
            rr = r.get("rerank_score")
            row.append(f"{rr:.4f}" if rr is not None else "")
        row.extend([
            r["account_name"], r["region"], r["product_group"],
            r["sales_area"], r["service_agent_id"],
        ])
        out.append(row)
    return out


def _print_score_details(rows: list[dict]) -> None:
    print("\nPer-pipeline scoreDetails (top result):")
    if not rows:
        print("  (no rows returned)")
        return
    top = rows[0]
    if "scoreDetails" not in top:
        # Surface the field set so the next step is obvious: either the
        # cluster's $rankFusion build hasn't shipped scoreDetails meta
        # yet, or an upstream projection is dropping it.
        keys = sorted(k for k in top.keys() if k != "embedding")
        print("  scoreDetails field absent from result row.")
        print(f"  available keys on top row: {keys}")
        return
    if top["scoreDetails"] is None:
        print("  scoreDetails present but null — $meta 'searchScoreDetails' "
              "returned no metadata for this row.")
        return
    import json
    print(json.dumps(top["scoreDetails"], indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True,
                        help="Misspelled or partial account_name from the inbound email.")
    parser.add_argument("--product", default="Software")
    parser.add_argument("--region", default=None,
                        help="Pre-filter region; omit for global search.")
    parser.add_argument("-k", type=int, default=5,
                        help="Final number of rows to display (default: 5).")
    parser.add_argument("--candidates", type=int, default=25,
                        help="Candidates fetched per inner pipeline before "
                             "fusion (default: 25).")
    parser.add_argument("--weight-vector", type=float, default=1.0,
                        help="RRF weight for the vector arm (default: 1.0).")
    parser.add_argument("--weight-bm25", type=float, default=1.0,
                        help="RRF weight for the BM25 arm (default: 1.0).")
    parser.add_argument("--score-details", action="store_true",
                        help="Surface per-pipeline rank/score breakdown via "
                             "$meta: 'scoreDetails' (Preview feature).")
    parser.add_argument("--rerank", action="store_true",
                        help="Pipe the fused result set through Voyage rerank.")
    args = parser.parse_args()

    settings = load_settings()

    with MongoClient(settings.mongo_uri) as client:
        coll = client[settings.mongo_db][settings.mongo_collection]

        # Untimed warm-up against the same indexes the timed query will use.
        warm_vec = embed_account(
            "__warmup__", args.product, settings.voyage_api_key,
            settings.voyage_model, settings.embed_dim,
        )
        list(coll.aggregate(_build_pipeline(
            query_vec=warm_vec, query="__warmup__", region=args.region,
            candidates=args.candidates, final_k=args.k,
            vector_index=settings.atlas_vector_index,
            search_index=settings.atlas_search_index,
            weight_vector=args.weight_vector, weight_bm25=args.weight_bm25,
            score_details=args.score_details,
        )))

        query_vec = embed_account(
            args.query, args.product, settings.voyage_api_key,
            settings.voyage_model, settings.embed_dim,
        )
        pipeline = _build_pipeline(
            query_vec=query_vec, query=args.query, region=args.region,
            candidates=args.candidates,
            # Fetch the full candidate pool when reranking; otherwise the
            # rerank arm has nothing past the top-k to re-order.
            final_k=args.candidates if args.rerank else args.k,
            vector_index=settings.atlas_vector_index,
            search_index=settings.atlas_search_index,
            weight_vector=args.weight_vector, weight_bm25=args.weight_bm25,
            score_details=args.score_details,
        )
        start = time.perf_counter()
        rows = list(coll.aggregate(pipeline))
        fusion_ms = (time.perf_counter() - start) * 1000.0

    rerank_ms = 0.0
    if args.rerank:
        rows, rerank_ms = voyage_rerank(
            args.query, rows,
            api_key=settings.voyage_api_key,
            model=settings.voyage_rerank_model,
            top_k=args.k,
        )

    print(f"\nIncoming query: {args.query!r}  product={args.product}  "
          f"region={args.region or 'ALL'}  k={args.k}  candidates={args.candidates}")
    print(f"weights: vector={args.weight_vector}  bm25={args.weight_bm25}")
    print(f"$rankFusion latency: {fusion_ms:7.1f} ms"
          + (f"  |  rerank latency: {rerank_ms:7.1f} ms" if args.rerank else ""))
    print()

    headers = ["fused"]
    if args.rerank:
        headers.append("rerank")
    headers += ["account_name", "region", "product_group", "sales_area", "agent_id"]
    print(tabulate(_format_rows(rows[: args.k], with_rerank=args.rerank),
                   headers=headers, tablefmt="github"))

    if args.score_details:
        _print_score_details(rows)


if __name__ == "__main__":
    main()
