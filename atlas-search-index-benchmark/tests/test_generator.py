from generator import (FIELD_COUNT, document_fingerprint, iter_documents,
                       make_document, query_terms)


def test_generation_is_deterministic():
    a = make_document(123, seed=42)
    b = make_document(123, seed=42)
    assert a == b
    assert document_fingerprint(a) == document_fingerprint(b)


def test_different_seq_gives_unique_ids_and_different_docs():
    a = make_document(1)
    b = make_document(2)
    assert a["_id"] != b["_id"]
    assert a != b


def test_document_has_approximately_20_fields():
    doc = make_document(7)
    assert 18 <= len(doc) <= 22, sorted(doc)


def test_document_has_array_fields():
    doc = make_document(9)
    assert isinstance(doc["tags"], list)
    assert isinstance(doc["authors"], list) and doc["authors"]
    assert isinstance(doc["line_items"], list) and doc["line_items"]


def test_field_types_and_ranges():
    doc = make_document(11)
    assert isinstance(doc["priority"], int) and 1 <= doc["priority"] <= 5
    assert isinstance(doc["is_public"], bool)
    assert doc["status"] in {"active", "pending", "archived", "draft", "review"}
    assert doc["score"] >= 0


def test_iteration_slice_is_deterministic_and_ordered():
    docs = list(iter_documents(3, seed=7, start=100))
    assert [d["_id"] for d in docs] == ["bench-00000100", "bench-00000101", "bench-00000102"]
    assert docs == list(iter_documents(3, seed=7, start=100))


def test_query_terms_deterministic():
    assert query_terms(42) == query_terms(42)
    assert query_terms(42) != query_terms(43)
