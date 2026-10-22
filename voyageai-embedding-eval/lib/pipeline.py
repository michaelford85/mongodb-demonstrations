"""The evaluation run: sample -> embed -> index -> retrieve -> score.

Both models go through identical steps over identical inputs:
same sampled documents, same document string, same queries, same qrels, same
retrieval depth and the same Atlas `$vectorSearch` settings. Only the embedding
model (and therefore the collection, vector field contents and index
dimensions) differs.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Callable

from lib import metrics
from lib.cache import EmbeddingCache, cache_key
from lib.config import (ConfigError, EvalError, ProviderConfig, RunParams, Settings, redacted,
                        validate_live)
from lib.dataset import Dataset, doc_text, load_beir, sample_dataset
from lib.mock import MockProvider, synthetic_dataset
from lib.providers import DOCUMENT, QUERY, EmbeddingProvider, build_provider
from lib.store import (SIMILARITY, VECTOR_FIELD, AtlasStore, MemoryStore, index_definition,
                       num_candidates_for, vector_search_pipeline)

Progress = Callable[[float, str], None]


def slug(text: str, limit: int = 24) -> str:
    out = "".join(c if c.isalnum() else "_" for c in text.lower()).strip("_")
    return out[:limit]


def collection_name(settings: Settings, params: RunParams, role: str, cfg: ProviderConfig,
                    mock: bool) -> str:
    """Deterministic and unique per model + sample, so runs never cross-contaminate."""
    sig = hashlib.sha256(
        f"{params.dataset}|{params.max_docs}|{params.seed}|{cfg.provider}|{cfg.model}|"
        f"{cfg.output_dimension}|{cfg.document_prefix!r}|{mock}".encode()).hexdigest()[:8]
    prefix = f"{settings.collection_prefix}{'_mock' if mock else ''}"
    return f"{prefix}_{slug(params.dataset, 12)}_{role}_{slug(cfg.model, 20)}_{sig}"


@dataclass
class ModelRun:
    role: str
    provider: str
    model: str
    dimensions: int
    collection: str
    index_name: str
    embed_seconds: float
    cache_hits: int
    rankings: dict[str, list[str]]


def _embed_cached(provider: EmbeddingProvider, texts: list[str], input_type: str,
                  cache: EmbeddingCache | None, progress: Progress, label: str, lo: float, hi: float):
    """Embed texts, reading/writing the cache. Returns (vectors, cache_hits)."""
    prefix = provider.cache_key_prefix(input_type)
    keys = [cache_key(prefix, t) for t in texts]
    cached = cache.get_many(keys) if cache else {}
    todo = [i for i, k in enumerate(keys) if k not in cached]
    if todo:
        def on_batch(done, total):
            progress(lo + (hi - lo) * done / total, f"{label}: embedded {done}/{total}")
        fresh = provider.embed([texts[i] for i in todo], input_type, on_batch)
        new = {keys[i]: v for i, v in zip(todo, fresh)}
        if cache:
            cache.put_many(new)
        cached.update(new)
    return [cached[k] for k in keys], len(texts) - len(todo)


def _make_providers(settings: Settings, mock: bool) -> dict[str, EmbeddingProvider]:
    if mock:
        v = ProviderConfig("mock", "mock-voyage")
        c = ProviderConfig("mock", "mock-competitor")
        return {"voyage": MockProvider(v, dim=128, noise=0.0), "competitor": MockProvider(c, dim=64, noise=0.15)}
    return {"voyage": build_provider(settings.voyage), "competitor": build_provider(settings.competitor)}


def _make_store(settings: Settings, mock: bool):
    if mock:
        return MemoryStore(), None
    from pymongo import MongoClient
    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=15000, appname="voyageai-embedding-eval")
    return AtlasStore(client, settings.db_name), client


def run_evaluation(settings: Settings, params: RunParams, mock: bool = False,
                   progress: Progress | None = None) -> dict:
    """Run the whole comparison and return a JSON-serialisable, secret-free result."""
    progress = progress or (lambda frac, msg: None)
    problems = params.validate()
    if not mock:
        problems += validate_live(settings)
    if problems:
        raise ConfigError(" ".join(problems))
    started = time.time()
    ks, depth = params.k_values, params.depth

    progress(0.02, "Loading dataset…")
    if mock:
        sample = synthetic_dataset(params.seed)
    else:
        sample = sample_dataset(load_beir(params.dataset, settings.data_dir), params.num_queries,
                                params.max_docs, params.seed)
    doc_ids = list(sample.corpus)
    doc_texts = [doc_text(sample.corpus[d]) for d in doc_ids]
    qids = list(sample.queries)
    q_texts = [sample.queries[q] for q in qids]

    providers = _make_providers(settings, mock)
    store, client = _make_store(settings, mock)
    cache = EmbeddingCache(settings.cache_dir) if (settings.use_cache and not mock) else None
    configs = {"voyage": settings.voyage, "competitor": settings.competitor}
    runs: dict[str, ModelRun] = {}
    try:
        for n, role in enumerate(("voyage", "competitor")):
            lo = 0.05 + 0.45 * n
            runs[role] = _run_model(role, providers[role], configs[role], settings, params, store, cache,
                                    doc_ids, doc_texts, qids, q_texts, mock, progress, lo, lo + 0.45)
    finally:
        if client:
            client.close()

    progress(0.97, "Scoring…")
    result = _score(settings, params, mock, sample, runs, depth, ks, time.time() - started)
    progress(1.0, "Done")
    return result


def _run_model(role, provider, cfg, settings, params, store, cache, doc_ids, doc_texts, qids, q_texts,
               mock, progress, lo, hi) -> ModelRun:
    label = f"{role} ({provider.model})"
    t0 = time.time()
    coll = collection_name(settings, params, role, cfg, mock)
    index = f"{coll}_vidx"[:120]

    progress(lo, f"{label}: probing vector dimension…")
    probe, _ = _embed_cached(provider, ["dimension probe"], DOCUMENT, cache, progress, label, lo, lo)
    dims = len(probe[0])
    progress(lo, f"{label}: {dims}-dimensional vectors; preparing collection and index…")
    store.prepare(coll, index, dims)

    present = store.existing_ids(coll)
    missing = [i for i, d in enumerate(doc_ids) if d not in present]
    hits = 0
    if missing:
        vecs, hits = _embed_cached(provider, [doc_texts[i] for i in missing], DOCUMENT, cache, progress,
                                   f"{label} documents", lo, lo + (hi - lo) * 0.6)
        if any(len(v) != dims for v in vecs):
            raise EvalError(f"{label}: vector length changed mid-run; refusing to mix dimensions.")
        store.insert(coll, [{"_id": doc_ids[i], VECTOR_FIELD: v, "model": provider.label}
                            for i, v in zip(missing, vecs)])
    progress(lo + (hi - lo) * 0.65, f"{label}: waiting for the vector index to be queryable…")
    store.wait_until_queryable(coll, index, on_wait=lambda s: progress(lo + (hi - lo) * 0.65,
                                                                       f"{label}: index status {s}…"))

    qvecs, qhits = _embed_cached(provider, q_texts, QUERY, cache, progress, f"{label} queries",
                                 lo + (hi - lo) * 0.7, lo + (hi - lo) * 0.85)
    rankings = {}
    for n, (qid, qv) in enumerate(zip(qids, qvecs), 1):
        if len(qv) != dims:
            raise EvalError(f"{label}: query vector has {len(qv)} dims, index expects {dims}.")
        rankings[qid] = store.search(coll, index, qv, params.depth)
        if n % 10 == 0 or n == len(qids):
            progress(lo + (hi - lo) * (0.85 + 0.15 * n / len(qids)), f"{label}: searched {n}/{len(qids)} queries")
    return ModelRun(role, provider.name, provider.model, dims, coll, index,
                    time.time() - t0, hits + qhits, rankings)


def _score(settings, params, mock, sample: Dataset, runs, depth, ks, elapsed) -> dict:
    scored = {}
    for role, run in runs.items():
        per_query, aggregate, skipped = metrics.evaluate_run(run.rankings, sample.qrels, ks)
        scored[role] = (per_query, aggregate, skipped)

    pq_v, pq_c = scored["voyage"][0], scored["competitor"][0]
    primary = f"ndcg@{depth}"
    comparisons = {m: metrics.compare_models(pq_v, pq_c, m, seed=params.seed) for m in next(iter(pq_v.values()), {})}

    n_rel = sum(1 for r in sample.qrels.values() if any(g > 0 for g in r.values()))
    caveats = [
        f"Sample: {len(sample.queries)} queries over {len(sample.corpus)} documents "
        f"(seed {params.seed}). Small samples give noisy results; the intervals below reflect only this sample.",
        "One public dataset and one document/query style. Results may not transfer to your data — "
        "evaluate on your own corpus and judgments before choosing a model.",
        "The corpus is subsampled, which is easier than the full benchmark; do not compare these numbers "
        "to published leaderboards.",
        "Retrieval uses approximate nearest-neighbour search (ANN) in Atlas; results can vary slightly "
        "between index builds.",
        "Public benchmark text may appear in either model's training data.",
        f"MRR and MAP are computed over the top {depth} results.",
    ]
    if mock:
        caveats.insert(0, "DRY RUN: synthetic data and fake hash-based embeddings. No model was called and "
                          "no database was touched. These numbers say nothing about real model quality.")
    caveats += sample.notes

    models = {}
    for role, run in runs.items():
        models[role] = {
            "provider": run.provider, "model": run.model, "dimensions": run.dimensions,
            "collection": run.collection, "index_name": run.index_name,
            "index_definition": index_definition(run.dimensions),
            "pipeline_template": vector_search_pipeline(run.index_name, f"<{run.dimensions} floats>", depth),
            "similarity": SIMILARITY, "num_candidates": num_candidates_for(depth),
            "seconds": round(run.embed_seconds, 1), "cache_hits": run.cache_hits,
            "aggregate": scored[role][1], "skipped_queries": scored[role][2],
        }
    per_query_rows = []
    for qid in sample.queries:
        if qid not in pq_v:
            continue
        row = {"query_id": qid, "query": sample.queries[qid], "n_relevant": sum(g > 0 for g in sample.qrels[qid].values())}
        for role, run in runs.items():
            row[role] = {"metrics": scored[role][0].get(qid), "ranked": run.rankings.get(qid, []),
                         "first_relevant_rank": metrics.first_relevant_rank(run.rankings.get(qid, []), sample.qrels[qid], depth)}
        per_query_rows.append(row)

    return {
        "status": "completed", "mock": mock, "elapsed_seconds": round(elapsed, 1),
        "config": redacted(settings, params),
        "dataset": {"name": sample.name, "queries": len(sample.queries), "documents": len(sample.corpus),
                    "scored_queries": n_rel},
        "ks": list(ks), "depth": depth, "primary_metric": primary,
        "models": models, "comparisons": comparisons, "per_query": per_query_rows, "caveats": caveats,
    }
