from atlas_client import AtlasAdminClient


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None):
        self.status_code = status_code
        self._body = body or {}
        self.headers = headers or {}

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, pages, token_body=None, fail_first_with=None):
        self.pages = list(pages)
        self.get_calls = []
        self.post_calls = []
        self.token_body = token_body or {"access_token": "tok", "expires_in": 3600, "token_type": "Bearer"}
        self.fail_first_with = fail_first_with
        self.sleeps = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs.get("params")))
        if self.fail_first_with is not None:
            status, headers = self.fail_first_with
            self.fail_first_with = None
            return FakeResponse(status_code=status, headers=headers)
        return self.pages.pop(0)

    def post(self, url, **kwargs):
        self.post_calls.append(url)
        return FakeResponse(body=self.token_body)


def page(items, total):
    return FakeResponse(body={"results": items, "totalCount": total, "links": []})


def make_client(session, sleeper=None):
    return AtlasAdminClient(
        org_id="5f0f1a2b3c4d5e6f7a8b9c0d",
        auth="service_account",
        client_id="cid",
        client_secret="secret",
        items_per_page=2,
        max_retries=3,
        session=session,
        sleeper=sleeper or (lambda s: None),
        clock=lambda: 1000.0,
    )


def test_pagination_walks_all_pages():
    projects = [{"id": f"p{i}", "name": f"proj{i}"} for i in range(5)]
    session = FakeSession(
        pages=[
            page(projects[0:2], 5),
            page(projects[2:4], 5),
            page(projects[4:5], 5),
        ]
    )
    client = make_client(session)
    collected = list(client.iter_projects())
    assert [p["id"] for p in collected] == [f"p{i}" for i in range(5)]
    params_sequence = [c[1] for c in session.get_calls]
    assert [p["pageNum"] for p in params_sequence] == [1, 2, 3]
    assert all(p["itemsPerPage"] == 2 for p in params_sequence)
    assert all(p["includeCount"] == "true" for p in params_sequence)


def test_pagination_stops_on_short_page_without_count():
    session = FakeSession(pages=[FakeResponse(body={"results": [{"id": "p0"}], "links": []})])
    client = make_client(session)
    assert len(list(client.iter_projects())) == 1
    assert len(session.get_calls) == 1


def test_token_requested_once_and_reused():
    projects = [{"id": "p0"}, {"id": "p1"}]
    session = FakeSession(
        pages=[page(projects, 2)],
    )
    client = make_client(session)
    list(client.iter_projects())
    assert len(session.post_calls) == 1
    assert session.post_calls[0].endswith("/api/oauth/token")


def test_retry_on_429_then_success():
    projects = [{"id": "p0"}, {"id": "p1"}]
    session = FakeSession(
        pages=[page(projects, 2)],
        fail_first_with=(429, {"Retry-After": "0"}),
    )
    sleeps = []
    client = make_client(session, sleeper=sleeps.append)
    collected = list(client.iter_projects())
    assert [p["id"] for p in collected] == ["p0", "p1"]
    assert len(sleeps) == 1
    assert len(session.get_calls) == 2


def test_error_after_retries_raises():
    from atlas_client import AtlasAPIError
    import pytest

    class AlwaysThrottled(FakeSession):
        def get(self, url, **kwargs):
            self.get_calls.append((url, kwargs.get("params")))
            return FakeResponse(status_code=429)

    session = AlwaysThrottled(pages=[])
    client = make_client(session)
    with pytest.raises(AtlasAPIError):
        list(client.iter_projects())
    assert len(session.get_calls) == 1 + client.max_retries


def test_items_per_page_clamped_to_api_max():
    session = FakeSession(pages=[])
    client = AtlasAdminClient(
        org_id="o",
        auth="api_key",
        public_key="pub",
        private_key="priv",
        items_per_page=999,
        session=session,
    )
    assert client.items_per_page == 500


def test_missing_credentials_rejected():
    import pytest

    with pytest.raises(ValueError):
        AtlasAdminClient(org_id="o", auth="service_account", client_id="", client_secret="")


def test_versioned_accept_headers_per_endpoint():
    class HeaderSession:
        def __init__(self):
            self.seen = []
            self.token_seen = False

        def get(self, url, **kwargs):
            self.seen.append((url, kwargs.get("headers", {}).get("Accept")))
            return FakeResponse(body={"results": [{"id": "x"}], "links": []})

        def post(self, url, **kwargs):
            self.token_seen = True
            return FakeResponse(body={"access_token": "t", "expires_in": 3600})

    session = HeaderSession()
    client = make_client(session)
    client.get_organization()
    list(client.iter_projects())
    list(client.iter_clusters("p1"))
    list(client.iter_processes("p1"))
    clusters_call = [c for c in session.seen if "/clusters" in c[0]][0]
    other_calls = [c for c in session.seen if "/clusters" not in c[0]]
    assert clusters_call[1] == "application/vnd.atlas.2024-08-05+json"
    assert all(c[1] == "application/vnd.atlas.2023-01-01+json" for c in other_calls)
