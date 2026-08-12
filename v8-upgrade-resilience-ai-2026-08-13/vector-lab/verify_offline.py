"""Offline verification: exercise every module without an Atlas cluster.

Fakes the $search / $vectorSearch stages by scoring the local corpus in Python,
so ranking logic, reranking, and the template render can all be checked.
"""
import json
import os
import sys
from pathlib import Path

LAB = Path(__file__).parent
os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true")
os.environ["EMBEDDING_PROVIDER"] = "offline"
os.environ["EMBEDDING_DIM"] = "256"
sys.path.insert(0, str(LAB / "app"))
sys.path.insert(0, str(LAB / "data"))

import config  # noqa: E402
import embeddings  # noqa: E402
import indexes  # noqa: E402
import search  # noqa: E402
import topics  # noqa: E402

ARTICLES = json.loads((LAB / "data" / "knowledge_base.json").read_text())
for a in ARTICLES:
    a[config.EMBEDDING_FIELD] = embeddings.offline_embedding(
        f"{a['title']}\n{a['body']}")


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


class FakeCollection:
    """Just enough of a collection to run the two pipelines locally."""

    def aggregate(self, pipeline):
        first = pipeline[0]
        if "$search" in first:
            query = first["$search"]["text"]["query"]
            limit = next(s["$limit"] for s in pipeline if "$limit" in s)
            terms = set(embeddings._tokens(query))
            scored = []
            for doc in ARTICLES:
                tokens = embeddings._tokens(f"{doc['title']} {doc['body']}")
                hits = sum(1 for t in tokens if t in terms)
                if hits:
                    scored.append((hits / (len(tokens) ** 0.5), doc))
            scored.sort(key=lambda p: -p[0])
            return [dict(d, score=round(s, 4)) for s, d in scored[:limit]]

        vs = first["$vectorSearch"]
        qv = vs["queryVector"]
        scored = [((_dot(qv, d[config.EMBEDDING_FIELD]) + 1) / 2, d)
                  for d in ARTICLES]
        scored.sort(key=lambda p: -p[0])
        return [dict(d, score=round(s, 6)) for s, d in scored[:vs["limit"]]]


config.get_articles = lambda: FakeCollection()

failures = []

text_doc = indexes.text_index_model().document
vec_doc = indexes.vector_index_model().document
assert text_doc["type"] == "search", text_doc
assert vec_doc["type"] == "vectorSearch", vec_doc
assert vec_doc["definition"]["fields"][0]["numDimensions"] == config.EMBEDDING_DIM
print(f"index models ok: {text_doc['name']}, {vec_doc['name']}")

v = embeddings.embed_query("why is my bill higher than last month")
assert len(v) == config.EMBEDDING_DIM, len(v)
assert abs(sum(x * x for x in v) - 1.0) < 1e-9, "not a unit vector"
assert embeddings.offline_embedding("abc") == embeddings.offline_embedding("abc")
assert len(embeddings.offline_embedding("the a an")) == config.EMBEDDING_DIM
print(f"embeddings ok: {config.EMBEDDING_DIM} dims, deterministic, normalised")

for mode in search.MODES:
    out = search.run(mode, "why is my bill higher than last month")
    assert out["mode"] == mode
    assert out["results"], f"{mode} returned nothing"
    assert len(out["results"]) <= config.RESULT_LIMIT
    for r in out["results"]:
        assert set(r) >= {"rank", "doc_id", "title", "snippet", "score",
                          "score_label"}, r
    assert json.dumps(out["pipeline"])
    print(f"{mode:8s} top: {out['results'][0]['title'][:58]}"
          f"  [{out['results'][0]['kind']}]")


def top_kinds(mode, query, n=3):
    return [r["kind"] for r in search.run(mode, query)["results"][:n]]


for query in topics.EXAMPLE_QUERIES:
    kw = top_kinds("keyword", query)
    vec = top_kinds("vector", query)
    rr = top_kinds("rerank", query)
    ok = "showcase" in vec or "showcase" in rr
    print(f"{'OK ' if ok else 'GAP'} {query[:46]:46s} "
          f"kw={kw} vec={vec} rr={rr}")
    if not ok:
        failures.append(query)

rr = search.run("rerank", "why is my bill higher than last month")
moves = [(r["moved_from"], r["rank"]) for r in rr["results"]]
assert all(m[0] for m in moves), "vector_rank missing"
print(f"rerank moves (vector#->rerank#): {moves[:5]}")

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

client = TestClient(main.app)
resp = client.get("/", params={"q": "why is my bill higher than last month"})
assert resp.status_code == 200, resp.status_code
assert "Keyword" in resp.text and "$vectorSearch" in resp.text
print(f"UI renders ok ({len(resp.text)} bytes)")

resp = client.get("/api/search", params={"q": "everything slows down after lunch"})
assert resp.status_code == 200
assert len(resp.json()["results"]) == 3
assert client.get("/api/search", params={"q": "x", "mode": "bogus"}).status_code == 400
assert client.get("/api/search", params={"q": "  "}).status_code == 400
print("api ok")

print("\nFAILURES:", failures or "none")
