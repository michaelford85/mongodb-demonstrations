import math

import pytest

from lib import metrics as m

QREL = {"a": 3, "b": 1, "z": 0}  # z has grade 0 -> not relevant


def test_ndcg_perfect_and_graded():
    assert m.ndcg_at_k(["a", "b"], QREL, 2) == pytest.approx(1.0)
    swapped = m.ndcg_at_k(["b", "a"], QREL, 2)
    ideal = 3 + 1 / math.log2(3)
    assert swapped == pytest.approx((1 + 3 / math.log2(3)) / ideal)


def test_ndcg_truncates_ideal_at_k():
    assert m.ndcg_at_k(["a"], QREL, 1) == pytest.approx(1.0)


def test_recall_precision_hand_computed():
    ranked = ["x", "a", "y", "b"]
    assert m.recall_at_k(ranked, QREL, 2) == 0.5
    assert m.recall_at_k(ranked, QREL, 4) == 1.0
    assert m.precision_at_k(ranked, QREL, 2) == 0.5
    assert m.precision_at_k(ranked, QREL, 4) == 0.5


def test_precision_divides_by_k_when_short_list():
    assert m.precision_at_k(["a"], QREL, 5) == pytest.approx(0.2)


def test_mrr_and_miss():
    assert m.reciprocal_rank(["x", "y", "b"], QREL, 10) == pytest.approx(1 / 3)
    assert m.reciprocal_rank(["x", "y"], QREL, 10) == 0.0
    assert m.reciprocal_rank(["x", "y", "b"], QREL, 2) == 0.0  # beyond depth


def test_average_precision_counts_unretrieved_relevant():
    # relevant at ranks 1 and 3 of 2 total: (1/1 + 2/3) / 2
    assert m.average_precision(["a", "x", "b"], QREL, 10) == pytest.approx((1 + 2 / 3) / 2)
    # only one of two found -> divided by 2
    assert m.average_precision(["a"], QREL, 10) == pytest.approx(0.5)


def test_duplicates_count_once():
    assert m.recall_at_k(["a", "a", "a"], QREL, 3) == 0.5
    assert m.precision_at_k(["a", "a", "b"], QREL, 3) == pytest.approx(2 / 3)


def test_empty_ranking_scores_zero():
    scores = m.evaluate_query([], QREL, (5, 10))
    assert all(v == 0 for v in scores.values())


def test_query_without_relevant_docs_is_none():
    assert m.evaluate_query(["a"], {"a": 0}, (5,)) is None
    assert m.evaluate_query(["a"], {}, (5,)) is None


def test_invalid_k_rejected():
    with pytest.raises(ValueError):
        m.ndcg_at_k(["a"], QREL, 0)


def test_evaluate_run_missing_query_scored_zero_and_unjudged_skipped():
    qrels = {"q1": {"a": 1}, "q2": {"b": 1}, "q3": {"c": 0}}
    per_q, agg, skipped = m.evaluate_run({"q1": ["a"]}, qrels, (5,))
    assert skipped == ["q3"]
    assert per_q["q1"]["recall@5"] == 1.0 and per_q["q2"]["recall@5"] == 0.0
    assert agg["recall@5"] == 0.5
    assert set(agg) == {"ndcg@5", "recall@5", "precision@5", "mrr@5", "map@5"}


def test_metric_names_use_depth_for_mrr_map():
    scores = m.evaluate_query(["a"], QREL, (5, 10))
    assert {"mrr@10", "map@10", "ndcg@5", "ndcg@10"} <= set(scores)


def test_compare_models_counts_and_is_seeded():
    a = {f"q{i}": {"ndcg@5": 1.0} for i in range(10)}
    b = {f"q{i}": {"ndcg@5": 0.5 if i < 6 else 1.0} for i in range(10)}
    r1 = m.compare_models(a, b, "ndcg@5", seed=1)
    assert (r1["wins_a"], r1["wins_b"], r1["ties"]) == (6, 0, 4)
    assert r1 == m.compare_models(a, b, "ndcg@5", seed=1)
    assert r1["ci_low"] <= r1["mean_diff"] <= r1["ci_high"]
    assert m.compare_models({}, {}, "ndcg@5")["n"] == 0
