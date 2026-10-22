"""Configuration: read the environment, validate it, and describe it without secrets.

Secrets (`MONGODB_URI`, API keys) are held in fields marked `repr=False` and are
never included in `redacted()`, status rows, error messages, or result files.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

SUPPORTED_PROVIDERS = ("openai", "cohere", "gemini")
SUPPORTED_DATASETS = ("scifact", "nfcorpus")
DEFAULT_VOYAGE_BASE_URL = "https://ai.mongodb.com/v1"

_PLACEHOLDER = re.compile(r"your[_-]|<[^>]+>|changeme", re.IGNORECASE)


class EvalError(Exception):
    """Base class for errors whose message is safe to show to the user."""


class ConfigError(EvalError):
    """Missing or invalid configuration."""


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    api_key: str = field(default="", repr=False)
    base_url: str = ""
    output_dimension: int | None = None
    # Text prepended to every document / query before embedding (e.g. E5-style instructions).
    document_prefix: str = ""
    query_prefix: str = ""

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass(frozen=True)
class RunParams:
    """Everything that changes the evaluation result (and nothing secret)."""
    dataset: str = "scifact"
    num_queries: int = 50
    max_docs: int = 1000
    seed: int = 42
    k_values: tuple[int, ...] = (5, 10)

    @property
    def depth(self) -> int:
        return max(self.k_values)

    def validate(self) -> list[str]:
        problems = []
        if self.dataset not in SUPPORTED_DATASETS:
            problems.append(f"Dataset must be one of {', '.join(SUPPORTED_DATASETS)}.")
        if self.num_queries < 1:
            problems.append("Number of queries must be at least 1.")
        if self.max_docs < 1:
            problems.append("Corpus size must be at least 1.")
        if not self.k_values or any(k < 1 for k in self.k_values):
            problems.append("k values must be positive integers.")
        elif len(set(self.k_values)) != len(self.k_values):
            problems.append("k values must be unique.")
        elif self.depth > 100:
            problems.append("Largest k must be 100 or less.")
        return problems


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str = field(default="", repr=False)
    db_name: str = "embedding_eval"
    collection_prefix: str = "embeval"
    voyage: ProviderConfig = ProviderConfig("voyage", "voyage-4", base_url=DEFAULT_VOYAGE_BASE_URL)
    competitor: ProviderConfig = ProviderConfig("openai", "text-embedding-3-large")
    defaults: RunParams = RunParams()
    use_cache: bool = True
    cache_dir: str = ".cache"
    data_dir: str = "data"


def _int_or_none(env: dict, name: str) -> int | None:
    raw = (env.get(name) or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number (got a non-numeric value).") from None
    if value < 1:
        raise ConfigError(f"{name} must be positive.")
    return value


def _int(env: dict, name: str, default: int) -> int:
    value = _int_or_none(env, name)
    return default if value is None else value


def _prefix(env: dict, name: str) -> str:
    """Raw (unstripped) prefix; a literal backslash-n in the value becomes a newline."""
    return (env.get(name) or "").replace("\\n", "\n")


def _seed(env: dict) -> int:
    raw = (env.get("EVAL_SEED") or "42").strip()
    try:
        return int(raw)
    except ValueError:
        raise ConfigError("EVAL_SEED must be a whole number.") from None


def parse_k_values(raw: str) -> tuple[int, ...]:
    try:
        ks = tuple(int(p) for p in raw.replace(" ", "").split(",") if p)
    except ValueError:
        raise ConfigError("EVAL_K_VALUES must be comma-separated whole numbers, e.g. 5,10.") from None
    return tuple(sorted(set(ks)))


def load_settings(env: dict | None = None) -> Settings:
    """Build Settings from environment variables (call load_dotenv() first)."""
    env = dict(os.environ if env is None else env)
    get = lambda name, default="": (env.get(name) if env.get(name) is not None else default).strip()  # noqa: E731
    return Settings(
        mongodb_uri=get("MONGODB_URI"),
        db_name=get("DB_NAME", "embedding_eval") or "embedding_eval",
        collection_prefix=get("COLLECTION_PREFIX", "embeval") or "embeval",
        voyage=ProviderConfig(
            provider="voyage",
            model=get("VOYAGE_MODEL", "voyage-4") or "voyage-4",
            api_key=get("VOYAGE_API_KEY"),
            base_url=(get("VOYAGE_BASE_URL") or DEFAULT_VOYAGE_BASE_URL).rstrip("/"),
            output_dimension=_int_or_none(env, "VOYAGE_OUTPUT_DIMENSION"),
        ),
        competitor=ProviderConfig(
            provider=get("COMPETITOR_EMBEDDING_PROVIDER", "openai").lower() or "openai",
            model=get("COMPETITOR_EMBEDDING_MODEL"),
            api_key=get("COMPETITOR_API_KEY"),
            base_url=get("COMPETITOR_BASE_URL").rstrip("/"),
            output_dimension=_int_or_none(env, "COMPETITOR_OUTPUT_DIMENSION"),
            document_prefix=_prefix(env, "COMPETITOR_DOCUMENT_PREFIX"),
            query_prefix=_prefix(env, "COMPETITOR_QUERY_PREFIX"),
        ),
        defaults=RunParams(
            dataset=get("EVAL_DATASET", "scifact") or "scifact",
            num_queries=_int(env, "EVAL_NUM_QUERIES", 50),
            max_docs=_int(env, "EVAL_MAX_DOCS", 1000),
            seed=_seed(env),
            k_values=parse_k_values(get("EVAL_K_VALUES", "5,10")) or (5, 10),
        ),
        use_cache=get("EVAL_USE_CACHE", "true").lower() not in ("0", "false", "no", "off"),
    )


def is_placeholder(value: str) -> bool:
    return not value or bool(_PLACEHOLDER.search(value))


def uri_host(uri: str) -> str:
    """Host portion of a connection string — never the credentials."""
    try:
        return urlparse(uri).hostname or "unparseable"
    except ValueError:
        return "unparseable"


def check_provider(cfg: ProviderConfig, name: str) -> list[str]:
    problems = []
    if cfg.provider != "voyage" and cfg.provider not in SUPPORTED_PROVIDERS:
        problems.append(
            f"{name}: unsupported provider '{cfg.provider}'. Use one of {', '.join(SUPPORTED_PROVIDERS)}."
        )
    if not cfg.model:
        problems.append(f"{name}: model is not set.")
    if is_placeholder(cfg.api_key):
        key_var = "VOYAGE_API_KEY" if cfg.provider == "voyage" else "COMPETITOR_API_KEY"
        problems.append(f"{name}: {key_var} is missing or still a placeholder.")
    if cfg.base_url and not cfg.base_url.startswith(("http://", "https://")):
        problems.append(f"{name}: base URL must start with http:// or https://.")
    if cfg.base_url.startswith("http://") and "localhost" not in cfg.base_url and "127.0.0.1" not in cfg.base_url:
        problems.append(f"{name}: refusing to send an API key over plain http:// to a non-local host.")
    return problems


def validate_live(settings: Settings) -> list[str]:
    """Problems that block a live run. An empty list means ready."""
    problems = check_provider(settings.voyage, "Voyage")
    problems += check_provider(settings.competitor, "Competitor")
    uri = settings.mongodb_uri
    if is_placeholder(uri):
        problems.append("MONGODB_URI is missing or still a placeholder.")
    elif not uri.startswith(("mongodb+srv://", "mongodb://")):
        problems.append("MONGODB_URI must start with mongodb+srv:// or mongodb://.")
    if settings.voyage.label == settings.competitor.label and (
        settings.voyage.output_dimension == settings.competitor.output_dimension
    ):
        problems.append("Voyage and the competitor are configured as the same model.")
    return problems


def status_rows(settings: Settings) -> list[dict]:
    """Configuration status for display — presence only, never values."""
    def row(item, ok, detail):
        return {"Item": item, "Status": "OK" if ok else "Needs attention", "Detail": detail}

    rows = [
        row("MongoDB Atlas URI", not is_placeholder(settings.mongodb_uri),
            f"host: {uri_host(settings.mongodb_uri)}" if not is_placeholder(settings.mongodb_uri)
            else "MONGODB_URI not set"),
        row("Voyage API key", not is_placeholder(settings.voyage.api_key),
            f"configured; endpoint {settings.voyage.base_url}" if not is_placeholder(settings.voyage.api_key)
            else "VOYAGE_API_KEY not set"),
        row("Voyage model", bool(settings.voyage.model), settings.voyage.model or "VOYAGE_MODEL not set"),
        row("Competitor provider", settings.competitor.provider in SUPPORTED_PROVIDERS,
            settings.competitor.provider),
        row("Competitor model", bool(settings.competitor.model),
            settings.competitor.model or "COMPETITOR_EMBEDDING_MODEL not set"),
        row("Competitor API key", not is_placeholder(settings.competitor.api_key),
            "configured" if not is_placeholder(settings.competitor.api_key) else "COMPETITOR_API_KEY not set"),
    ]
    return rows


def redacted(settings: Settings, params: RunParams) -> dict:
    """The run configuration with every secret removed."""
    def prov(cfg: ProviderConfig):
        return {
            "provider": cfg.provider,
            "model": cfg.model,
            "base_url": cfg.base_url or "(provider default)",
            "output_dimension": cfg.output_dimension or "(model default)",
            "document_prefix": cfg.document_prefix or "(none)",
            "query_prefix": cfg.query_prefix or "(none)",
            "api_key": "configured" if not is_placeholder(cfg.api_key) else "not set",
        }

    return {
        "atlas": {
            "uri": "configured" if not is_placeholder(settings.mongodb_uri) else "not set",
            "host": uri_host(settings.mongodb_uri) if not is_placeholder(settings.mongodb_uri) else None,
            "database": settings.db_name,
            "collection_prefix": settings.collection_prefix,
        },
        "voyage": prov(settings.voyage),
        "competitor": prov(settings.competitor),
        "run": {
            "dataset": params.dataset,
            "num_queries": params.num_queries,
            "max_docs": params.max_docs,
            "seed": params.seed,
            "k_values": list(params.k_values),
            "retrieval_depth": params.depth,
        },
        "use_cache": settings.use_cache,
    }
