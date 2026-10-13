"""Retrieval metrics, written out plainly so the formulas are easy to audit.

Data roles (kept separate on purpose):
    queries : {query_id: query_text}
    qrels   : {query_id: {doc_id: relevance_grade}}   grade > 0 means relevant
    ranked  : [doc_id, ...] best first — one model's answer for one query

Conventions
    * Duplicate doc IDs in `ranked` count once, at their first position.
    * Only grades > 0 are relevant. SciFact/NFCorpus-style grades are used as
      graded gains by NDCG and as binary relevance by every other metric.
    * Queries with no relevant document cannot be scored and are skipped.
    * Precision@k divides by k even if fewer than k documents were returned.
    * MRR and MAP are computed over the retrieval depth (the largest k):
      MAP divides by the TOTAL number of relevant documents, so relevant
      documents beyond the depth count as misses.
"""
from __future__ import annotations

import math
import random
from statistics import mean


def _dedupe(ranked: list[str]) -> list[str]:
    seen, out = set(), []
    for doc in ranked:
        if doc not in seen:
            seen.add(doc)
            out.append(doc)
    return out


def _check_k(k: int) -> None:
    if k < 1:
        raise ValueError("k must be at least 1")


def relevant_docs(qrel: dict[str, int]) -> dict[str, int]:
    return {d: g for d, g in qrel.items() if g > 0}


def dcg(gains: list[float]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(ranked, qrel, k):
    """DCG of the top k (gain = grade, discount = log2(rank+1)) over the ideal DCG."""
    _check_k(k)
    rel = relevant_docs(qrel)
    if not rel:
        return None
    gains = [rel.get(d, 0) for d in _dedupe(ranked)[:k]]
    ideal = dcg(sorted(rel.values(), reverse=True)[:k])
    return dcg(gains) / ideal


def recall_at_k(ranked, qrel, k):
    _check_k(k)
    rel = relevant_docs(qrel)
    if not rel:
        return None
    return sum(1 for d in _dedupe(ranked)[:k] if d in rel) / len(rel)


def precision_at_k(ranked, qrel, k):
    _check_k(k)
    rel = relevant_docs(qrel)
    if not rel:
        return None
    return sum(1 for d in _dedupe(ranked)[:k] if d in rel) / k


def reciprocal_rank(ranked, qrel, depth):
    """1 / rank of the first relevant document within `depth`, else 0."""
    _check_k(depth)
    rel = relevant_docs(qrel)
    if not rel:
        return None
    for i, d in enumerate(_dedupe(ranked)[:depth], start=1):
        if d in rel:
            return 1.0 / i
    return 0.0


def average_precision(ranked, qrel, depth):
    """Mean of precision@i at every rank i holding a relevant doc, over ALL relevant docs."""
    _check_k(depth)
    rel = relevant_docs(qrel)
    if not rel:
        return None
    hits, total = 0, 0.0
    for i, d in enumerate(_dedupe(ranked)[:depth], start=1):
        if d in rel:
            hits += 1
            total += hits / i
    return total / len(rel)


def first_relevant_rank(ranked, qrel, depth) -> int | None:
    rel = relevant_docs(qrel)
    for i, d in enumerate(_dedupe(ranked)[:depth], start=1):
        if d in rel:
            return i
    return None


def evaluate_query(ranked, qrel, ks) -> dict[str, float] | None:
    """All metrics for one query, or None if it has no relevant document."""
    if not relevant_docs(qrel):
        return None
    depth = max(ks)
    out: dict[str, float] = {}
    for k in ks:
        out[f"ndcg@{k}"] = ndcg_at_k(ranked, qrel, k)
        out[f"recall@{k}"] = recall_at_k(ranked, qrel, k)
        out[f"precision@{k}"] = precision_at_k(ranked, qrel, k)
    out[f"mrr@{depth}"] = reciprocal_rank(ranked, qrel, depth)
    out[f"map@{depth}"] = average_precision(ranked, qrel, depth)
    return out


def evaluate_run(run: dict[str, list[str]], qrels: dict[str, dict[str, int]], ks):
    """Score every query. Returns (per_query, aggregate, skipped_query_ids).

    A query missing from `run` is scored as an empty ranking (all zeros) rather
    than silently dropped, so a retrieval failure cannot inflate the average.
    """
    per_query, skipped = {}, []
    for qid, qrel in qrels.items():
        scores = evaluate_query(run.get(qid, []), qrel, ks)
        if scores is None:
            skipped.append(qid)
        else:
            per_query[qid] = scores
    aggregate = {}
    if per_query:
        for metric in next(iter(per_query.values())):
            aggregate[metric] = mean(s[metric] for s in per_query.values())
    return per_query, aggregate, skipped


def compare_models(per_query_a, per_query_b, metric, seed=0, n_boot=2000, eps=1e-9):
    """Paired comparison of A minus B on one metric, over queries both scored.

    Returns win/loss/tie counts and a seeded bootstrap 95% interval for the mean
    difference. The interval only reflects sampling of THESE queries; it says
    nothing about other datasets, domains, or query styles.
    """
    qids = sorted(set(per_query_a) & set(per_query_b))
    diffs = [per_query_a[q][metric] - per_query_b[q][metric] for q in qids]
    if not diffs:
        return {"n": 0, "wins_a": 0, "wins_b": 0, "ties": 0, "mean_diff": None, "ci_low": None, "ci_high": None}
    rng = random.Random(seed)
    n = len(diffs)
    boots = sorted(mean(diffs[rng.randrange(n)] for _ in range(n)) for _ in range(n_boot))
    return {
        "n": n,
        "wins_a": sum(d > eps for d in diffs),
        "wins_b": sum(d < -eps for d in diffs),
        "ties": sum(abs(d) <= eps for d in diffs),
        "mean_diff": mean(diffs),
        "ci_low": boots[int(0.025 * n_boot)],
        "ci_high": boots[int(0.975 * n_boot) - 1],
    }
