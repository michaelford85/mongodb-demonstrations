import base64
import time

import requests


class AtlasAPIError(RuntimeError):
    pass


RETRYABLE_STATUS = {429, 500, 502, 503, 504}
BASE_URL = "https://cloud.mongodb.com"


class AtlasAdminClient:
    def __init__(
        self,
        org_id: str,
        auth: str = "service_account",
        client_id: str = "",
        client_secret: str = "",
        public_key: str = "",
        private_key: str = "",
        items_per_page: int = 100,
        timeout: float = 20.0,
        max_retries: int = 4,
        base_url: str = BASE_URL,
        session=None,
        sleeper=time.sleep,
        clock=time.time,
    ):
        if auth not in {"service_account", "api_key"}:
            raise ValueError(f"unsupported ATLAS_AUTH: {auth}")
        if auth == "service_account" and not (client_id and client_secret):
            raise ValueError("service_account auth requires ATLAS_CLIENT_ID and ATLAS_CLIENT_SECRET")
        if auth == "api_key" and not (public_key and private_key):
            raise ValueError("api_key auth requires ATLAS_PUBLIC_KEY and ATLAS_PRIVATE_KEY")
        self.org_id = org_id
        self.auth = auth
        self.client_id = client_id
        self.client_secret = client_secret
        self.public_key = public_key
        self.private_key = private_key
        self.items_per_page = min(max(items_per_page, 1), 500)
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.sleeper = sleeper
        self.clock = clock
        self._token = None
        self._token_expires_at = 0.0

    def _bearer_token(self) -> str:
        if self.auth != "service_account":
            raise AtlasAPIError("bearer token requested while using api_key auth")
        now = self.clock()
        if self._token and now < self._token_expires_at:
            return self._token
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        resp = self.session.post(
            f"{self.base_url}/api/oauth/token",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data="grant_type=client_credentials",
            timeout=self.timeout,
        )
        self._raise_for_status(resp, "token request")
        body = resp.json()
        self._token = body["access_token"]
        self._token_expires_at = now + int(body.get("expires_in", 3600)) - 60
        return self._token

    def _request(self, path: str, params: dict, accept: str = "application/vnd.atlas.2023-01-01+json") -> dict:
        attempt = 0
        while True:
            headers = {"Accept": accept}
            if self.auth == "service_account":
                headers["Authorization"] = f"Bearer {self._bearer_token()}"
            else:
                from requests.auth import HTTPDigestAuth

                self.session.auth = HTTPDigestAuth(self.public_key, self.private_key)
            resp = self.session.get(
                f"{self.base_url}{path}", headers=headers, params=params, timeout=self.timeout
            )
            if resp.status_code in RETRYABLE_STATUS and attempt < self.max_retries:
                attempt += 1
                delay = float(resp.headers.get("Retry-After", 0)) or min(0.5 * (2 ** (attempt - 1)), 8.0)
                self.sleeper(delay)
                continue
            self._raise_for_status(resp, f"GET {path}")
            return resp.json()

    def _raise_for_status(self, resp, context: str):
        if resp.status_code >= 400:
            try:
                detail = resp.json()
                detail = detail.get("detail") or detail.get("reason") or str(detail)
            except Exception:
                detail = resp.text[:500]
            raise AtlasAPIError(
                f"Atlas API error ({resp.status_code}) during {context}: {detail}"
            )

    def _paginate(self, path: str, extra_params: dict | None = None, accept: str = "application/vnd.atlas.2023-01-01+json"):
        page_num = 1
        seen = 0
        while True:
            params = {
                "pageNum": page_num,
                "itemsPerPage": self.items_per_page,
                "includeCount": "true",
            }
            if extra_params:
                params.update(extra_params)
            body = self._request(path, params, accept=accept)
            results = body.get("results", [])
            yield from results
            seen += len(results)
            total = body.get("totalCount")
            if not results or len(results) < self.items_per_page:
                return
            if total is not None and seen >= total:
                return
            page_num += 1

    def get_organization(self) -> dict:
        body = self._request(f"/api/atlas/v2/orgs/{self.org_id}", {})
        return body

    def iter_projects(self):
        yield from self._paginate(f"/api/atlas/v2/orgs/{self.org_id}/groups")

    def iter_clusters(self, project_id: str):
        yield from self._paginate(
            f"/api/atlas/v2/groups/{project_id}/clusters",
            accept="application/vnd.atlas.2024-08-05+json",
        )

    def iter_processes(self, project_id: str):
        yield from self._paginate(f"/api/atlas/v2/groups/{project_id}/processes")
