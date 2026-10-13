import json

import pytest

from lib.cache import EmbeddingCache, cache_key
from lib.config import ConfigError, RunParams, load_settings
from lib.dataset import parse_beir, sample_dataset
from lib.mock import synthetic_dataset
from lib.pipeline import collection_name, run_evaluation
from lib.store import (MemoryStore, StoreError, index_definition, num_candidates_for,
                       vector_search_pipeline)

CORPUS = "\n".join(json.dumps({"_id": f"d{i}", "title": f"T{i}", "text": f"text {i}"}) for i in range(20))
QUERIES = "\n".join(json.dumps({"_id": f"q{i}", "text": f"query {i}"}) for i in range(6))
QRELS = "query-id\tcorpus-id\tscore\n" + "\n".join(f"q{i}\td{i}\t1" for i in range(5)) + "\nq5\td5\t0\n"


def test_parse_and_sample_is_seeded_and_keeps_relevant_docs():
    ds = parse_beir("t", CORPUS, QUERIES, QRELS)
    assert len(ds.corpus) == 20 and ds.qrels["q0"] == {"d0": 1}
    a, b = sample_dataset(ds, 3, 8, seed=1), sample_dataset(ds, 3, 8, seed=1)
    assert a.queries == b.queries and list(a.corpus) == list(b.corpus)
    assert "q5" not in a.queries                      # q5 has no positive judgment
    assert len(a.corpus) == 8
    for qid, rel in a.qrels.items():
        assert all(d in a.corpus for d in rel)


def test_sample_raises_corpus_when_too_small_and_notes_it():
    ds = parse_beir("t", CORPUS, QUERIES, QRELS)
    s = sample_dataset(ds, 5, 2, seed=0)
    assert len(s.corpus) == 5 and any("raised" in n for n in s.notes)


def test_cache_roundtrip_and_key_isolation(tmp_path):
    cache = EmbeddingCache(tmp_path)
    k1, k2 = cache_key("p|model1", "text"), cache_key("p|model2", "text")
    assert k1 != k2
    cache.put_many({k1: [0.5, 0.25]})
    got = cache.get_many([k1, k2])
    assert got == {k1: [0.5, 0.25]}


def test_pipeline_and_index_definition_are_explicit():
    assert index_definition(8) == {"fields": [{"type": "vector", "path": "embedding",
                                               "numDimensions": 8, "similarity": "cosine"}]}
    stage = vector_search_pipeline("idx", [0.1], 10)[0]["$vectorSearch"]
    assert stage["limit"] == 10 and stage["numCandidates"] == 200 and stage["index"] == "idx"
    assert num_candidates_for(1) == 100 and num_candidates_for(10000) == 10000


def test_memory_store_search_orders_by_cosine():
    s = MemoryStore()
    s.prepare("c", "i", 2)
    s.insert("c", [{"_id": "x", "embedding": [1, 0]}, {"_id": "y", "embedding": [0, 1]}])
    assert s.search("c", "i", [0.9, 0.1], 2) == ["x", "y"]
    assert s.existing_ids("c") == {"x", "y"}


def test_collection_names_isolate_models_and_samples():
    st = load_settings({})
    p = RunParams()
    from lib.config import ProviderConfig
    a = collection_name(st, p, "voyage", ProviderConfig("voyage", "voyage-4"), False)
    b = collection_name(st, p, "competitor", ProviderConfig("openai", "text-embedding-3-large"), False)
    c = collection_name(st, RunParams(max_docs=500), "voyage", ProviderConfig("voyage", "voyage-4"), False)
    d = collection_name(st, p, "voyage", ProviderConfig("voyage", "voyage-4", output_dimension=256), False)
    e = collection_name(st, p, "voyage", ProviderConfig("voyage", "voyage-4", document_prefix="passage: "), False)
    assert len({a, b, c, d, e}) == 5 and all(n.startswith("embeval_") for n in (a, b, c, d, e))


def test_dry_run_end_to_end_is_deterministic_and_offline():
    st = load_settings({})
    params = RunParams(k_values=(5, 10))
    r1 = run_evaluation(st, params, mock=True)
    r2 = run_evaluation(st, params, mock=True)
    assert r1["status"] == "completed" and r1["mock"] and r1["ks"] == [5, 10]
    assert r1["models"]["voyage"]["dimensions"] == 128 and r1["models"]["competitor"]["dimensions"] == 64
    assert r1["models"]["voyage"]["collection"] != r1["models"]["competitor"]["collection"]
    assert r1["models"]["voyage"]["aggregate"] == r2["models"]["voyage"]["aggregate"]
    assert 0 <= r1["models"]["voyage"]["aggregate"]["ndcg@10"] <= 1
    assert "DRY RUN" in r1["caveats"][0]
    secret_cfg = load_settings({"MONGODB_URI": "mongodb+srv://user:hunter2@c.example.net/", "VOYAGE_API_KEY": "k-secret-1"})
    leaked = json.dumps(run_evaluation(secret_cfg, params, mock=True)["config"])
    assert "hunter2" not in leaked and "k-secret-1" not in leaked
    progress = []
    run_evaluation(st, params, mock=True, progress=lambda f, m: progress.append(f))
    assert progress[-1] == 1.0 and progress == sorted(progress)


def test_live_run_blocked_without_credentials_and_makes_no_calls():
    with pytest.raises(ConfigError, match="VOYAGE_API_KEY"):
        run_evaluation(load_settings({}), RunParams(), mock=False)


def test_invalid_params_rejected_before_anything_runs():
    with pytest.raises(ConfigError):
        run_evaluation(load_settings({}), RunParams(k_values=()), mock=True)


def test_synthetic_dataset_is_deterministic():
    assert synthetic_dataset(1).queries == synthetic_dataset(1).queries


def test_atlas_store_refuses_dimension_mismatch_and_creates_missing_index():
    from unittest.mock import MagicMock

    from lib.store import AtlasStore

    client = MagicMock()
    db = client["db"]
    db.list_collection_names.return_value = ["c"]
    coll = db["c"]
    coll.list_search_indexes.return_value = iter([{"latestDefinition": {"fields": [
        {"path": "embedding", "numDimensions": 1024}]}}])
    with pytest.raises(StoreError, match="numDimensions=1024.*produces 512"):
        AtlasStore(client, "db").prepare("c", "idx", 512)
    coll.create_search_index.assert_not_called()

    coll.list_search_indexes.return_value = iter([])
    AtlasStore(client, "db").prepare("c", "idx", 512)
    model = coll.create_search_index.call_args.args[0]
    assert model.document["name"] == "idx" and model.document["type"] == "vectorSearch"
    assert model.document["definition"] == index_definition(512)
