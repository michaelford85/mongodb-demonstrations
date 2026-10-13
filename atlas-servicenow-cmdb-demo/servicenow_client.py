import time

import requests


class ServiceNowError(RuntimeError):
    pass


RETRYABLE_STATUS = {429, 500, 502, 503, 504}
SUBMIT_PATH = "/api/now/identifyreconcile"
SIMULATE_PATH = "/api/now/identifyreconcile/query"


class ServiceNowIREClient:
    def __init__(
        self,
        instance_url: str,
        username: str,
        password: str,
        discovery_source: str,
        timeout: float = 20.0,
        max_retries: int = 3,
        session=None,
        sleeper=time.sleep,
    ):
        if not instance_url:
            raise ServiceNowError("SERVICENOW_INSTANCE_URL is not configured")
        if not (username and password):
            raise ServiceNowError("SERVICENOW_USERNAME and SERVICENOW_PASSWORD are not configured")
        self.instance_url = instance_url.rstrip("/")
        self.username = username
        self.password = password
        self.discovery_source = discovery_source
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self.sleeper = sleeper

    def _post(self, path: str, payload: dict) -> dict:
        attempt = 0
        while True:
            resp = self.session.post(
                f"{self.instance_url}{path}",
                params={"sysparm_data_source": self.discovery_source},
                json=payload,
                auth=(self.username, self.password),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=self.timeout,
            )
            if resp.status_code in RETRYABLE_STATUS and attempt < self.max_retries:
                attempt += 1
                delay = float(resp.headers.get("Retry-After", 0)) or min(0.5 * (2 ** (attempt - 1)), 8.0)
                self.sleeper(delay)
                continue
            if resp.status_code >= 400:
                try:
                    detail = resp.json()
                    detail = str(detail)[:500]
                except Exception:
                    detail = resp.text[:500]
                raise ServiceNowError(
                    f"ServiceNow IRE API error ({resp.status_code}) on {path}: {detail}"
                )
            return resp.json()

    def simulate(self, payload: dict) -> dict:
        return self._post(SIMULATE_PATH, payload)

    def submit(self, payload: dict) -> dict:
        return self._post(SUBMIT_PATH, payload)


def ensure_apply_allowed(settings, cli_apply: bool):
    if not cli_apply:
        raise SystemExit(
            "Live writes are disabled: --apply was not given. "
            "Re-run with --apply (and SERVICENOW_ALLOW_WRITES=true) to write to ServiceNow."
        )
    if not settings.servicenow_allow_writes:
        raise SystemExit(
            "Live writes are disabled: SERVICENOW_ALLOW_WRITES is not 'true'. "
            "Set SERVICENOW_ALLOW_WRITES=true in .env AND pass --apply to enable writes. "
            "See the README for the risks before doing this."
        )
