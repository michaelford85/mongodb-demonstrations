import pytest

from lib.config import ProviderConfig
from lib.providers import DOCUMENT, QUERY, ProviderError, build_provider

KEY = "super-secret-key"


class FakeResp:
    def __init__(self, status=200, payload=None, headers=None, text=""):
        self.status_code, self._payload, self.headers, self.text = status, payload, headers or {}, text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self.responses.pop(0)


def make(provider, session, **kw):
    p = build_provider(ProviderConfig(provider, kw.pop("model", "m"), api_key=KEY, **kw))
    p._session, p._sleep = session, lambda s: None
    return p


def test_voyage_request_shape_and_ordering():
    s = FakeSession(FakeResp(payload={"data": [{"index": 1, "embedding": [0.2, 0.2]},
                                                {"index": 0, "embedding": [0.1, 0.1]}]}))
    p = make("voyage", s, model="voyage-4", base_url="https://ai.mongodb.com/v1", output_dimension=2)
    out = p.embed(["a", "b"], QUERY)
    assert out == [[0.1, 0.1], [0.2, 0.2]]
    call = s.calls[0]
    assert call["url"] == "https://ai.mongodb.com/v1/embeddings"
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    assert call["json"]["input_type"] == "query" and call["json"]["output_dimension"] == 2
    assert call["json"]["model"] == "voyage-4"


def test_voyage_document_mode():
    s = FakeSession(FakeResp(payload={"data": [{"index": 0, "embedding": [1.0]}]}))
    make("voyage", s).embed(["a"], DOCUMENT)
    assert s.calls[0]["json"]["input_type"] == "document"


def test_openai_shape_has_no_input_type_and_dimensions_param():
    s = FakeSession(FakeResp(payload={"data": [{"index": 0, "embedding": [1.0, 0.0]}]}))
    p = make("openai", s, model="text-embedding-3-large", output_dimension=2)
    p.embed(["a"], DOCUMENT)
    body = s.calls[0]["json"]
    assert "input_type" not in body and body["dimensions"] == 2 and body["encoding_format"] == "float"
    assert s.calls[0]["url"] == "https://api.openai.com/v1/embeddings"


def test_openai_custom_base_url():
    s = FakeSession(FakeResp(payload={"data": [{"index": 0, "embedding": [1.0]}]}))
    make("openai", s, base_url="https://proxy.example.com/v1/").embed(["a"], QUERY)
    assert s.calls[0]["url"] == "https://proxy.example.com/v1/embeddings"


@pytest.mark.parametrize("mode,expected", [(DOCUMENT, "search_document"), (QUERY, "search_query")])
def test_cohere_input_types_and_response(mode, expected):
    s = FakeSession(FakeResp(payload={"embeddings": {"float": [[0.5, 0.5]]}}))
    out = make("cohere", s, model="embed-v4.0").embed(["a"], mode)
    assert out == [[0.5, 0.5]]
    body = s.calls[0]["json"]
    assert body["input_type"] == expected and body["embedding_types"] == ["float"]
    assert s.calls[0]["url"] == "https://api.cohere.com/v2/embed"


@pytest.mark.parametrize("mode,expected", [(DOCUMENT, "RETRIEVAL_DOCUMENT"), (QUERY, "RETRIEVAL_QUERY")])
def test_gemini_task_types_key_in_header_not_url(mode, expected):
    s = FakeSession(FakeResp(payload={"embeddings": [{"values": [0.1, 0.2, 0.3]}]}))
    out = make("gemini", s, model="gemini-embedding-001", output_dimension=3).embed(["a"], mode)
    assert out == [[0.1, 0.2, 0.3]]
    call = s.calls[0]
    assert call["url"].endswith("/models/gemini-embedding-001:batchEmbedContents")
    assert KEY not in call["url"] and call["headers"]["x-goog-api-key"] == KEY
    req = call["json"]["requests"][0]
    assert req["taskType"] == expected and req["outputDimensionality"] == 3
    assert req["model"] == "models/gemini-embedding-001"


def test_batching_respects_provider_limit():
    p = make("cohere", FakeSession(), model="m")
    p.batch_size = 2
    p._session = FakeSession(*[FakeResp(payload={"embeddings": {"float": [[1.0], [1.0]][:n]}}) for n in (2, 2, 1)])
    out = p.embed(["a", "b", "c", "d", "e"], DOCUMENT)
    assert len(out) == 5 and [len(c["json"]["texts"]) for c in p._session.calls] == [2, 2, 1]


def test_retries_on_429_then_succeeds(monkeypatch):
    s = FakeSession(FakeResp(429, headers={"Retry-After": "1"}),
                    FakeResp(200, payload={"data": [{"index": 0, "embedding": [1.0]}]}))
    sleeps = []
    p = make("openai", s)
    p._sleep = sleeps.append
    assert p.embed(["a"], QUERY) == [[1.0]]
    assert sleeps == [1.0] and len(s.calls) == 2


def test_gives_up_after_max_retries():
    s = FakeSession(*[FakeResp(503) for _ in range(10)])
    with pytest.raises(ProviderError, match="giving up"):
        make("openai", s).embed(["a"], QUERY)


def test_auth_error_is_clear_and_not_retried():
    s = FakeSession(FakeResp(401, payload={"message": "bad key"}))
    with pytest.raises(ProviderError, match="authentication failed") as exc:
        make("voyage", s).embed(["a"], QUERY)
    assert KEY not in str(exc.value) and len(s.calls) == 1


def test_error_body_scrubs_echoed_key():
    s = FakeSession(FakeResp(400, payload={"message": f"invalid token {KEY}"}))
    with pytest.raises(ProviderError) as exc:
        make("openai", s).embed(["a"], QUERY)
    assert KEY not in str(exc.value) and "***" in str(exc.value)


def test_dimension_mismatch_with_requested_is_an_error_not_a_truncation():
    s = FakeSession(FakeResp(payload={"data": [{"index": 0, "embedding": [1.0, 2.0, 3.0]}]}))
    with pytest.raises(ProviderError, match="requested output dimension 2 but received 3"):
        make("openai", s, output_dimension=2).embed(["a"], QUERY)


def test_wrong_count_and_bad_shape():
    s = FakeSession(FakeResp(payload={"data": [{"index": 0, "embedding": [1.0]}]}))
    with pytest.raises(ProviderError, match="asked for 2"):
        make("openai", s).embed(["a", "b"], QUERY)
    with pytest.raises(ProviderError, match="unexpected response shape"):
        make("cohere", FakeSession(FakeResp(payload={"oops": 1}))).embed(["a"], QUERY)


def test_non_finite_rejected():
    s = FakeSession(FakeResp(payload={"data": [{"index": 0, "embedding": [float("nan")]}]}))
    with pytest.raises(ProviderError, match="non-finite"):
        make("openai", s).embed(["a"], QUERY)


def test_unknown_provider_and_bad_input_type():
    with pytest.raises(ProviderError, match="Unsupported provider"):
        build_provider(ProviderConfig("nope", "m"))
    with pytest.raises(ValueError):
        make("openai", FakeSession()).embed(["a"], "other")


def test_cache_key_differs_by_mode_model_dimension():
    a = make("openai", FakeSession(), model="m1")
    b = make("openai", FakeSession(), model="m2")
    c = make("openai", FakeSession(), model="m1", output_dimension=256)
    keys = {a.cache_key_prefix(DOCUMENT), a.cache_key_prefix(QUERY), b.cache_key_prefix(DOCUMENT),
            c.cache_key_prefix(DOCUMENT)}
    assert len(keys) == 4


def test_prefixes_applied_per_mode_and_change_cache_key():
    def run(mode):
        s = FakeSession(FakeResp(payload={"data": [{"index": 0, "embedding": [1.0]}]}))
        p = make("openai", s, query_prefix="Instruct: find\nQuery: ")
        p.embed(["hello"], mode)
        return p, s.calls[0]["json"]["input"]
    pq, sent_q = run(QUERY)
    pd_, sent_d = run(DOCUMENT)
    assert sent_q == ["Instruct: find\nQuery: hello"] and sent_d == ["hello"]
    assert pq.cache_key_prefix(QUERY) != make("openai", FakeSession()).cache_key_prefix(QUERY)
