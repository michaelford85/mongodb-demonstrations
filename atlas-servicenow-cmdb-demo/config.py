import json
import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    source: str = "mock"
    mapping_file: str = "mapping.json"

    atlas_org_id: str = ""
    atlas_auth: str = "service_account"
    atlas_client_id: str = ""
    atlas_client_secret: str = ""
    atlas_public_key: str = ""
    atlas_private_key: str = ""
    atlas_items_per_page: int = 100
    atlas_timeout_seconds: float = 20.0
    atlas_max_retries: int = 4

    servicenow_instance_url: str = ""
    servicenow_username: str = ""
    servicenow_password: str = ""
    servicenow_discovery_source: str = "atlas"
    servicenow_timeout_seconds: float = 20.0
    servicenow_max_retries: int = 3
    servicenow_allow_writes: bool = False


def _bool(value: str) -> bool:
    return (value or "").strip().lower() in {"true", "1", "yes"}


def load_settings(env=None) -> Settings:
    env = os.environ if env is None else env
    return Settings(
        source=env.get("DEMO_SOURCE", "mock").strip().lower() or "mock",
        mapping_file=env.get("DEMO_MAPPING_FILE", "mapping.json").strip() or "mapping.json",
        atlas_org_id=env.get("ATLAS_ORG_ID", "").strip(),
        atlas_auth=env.get("ATLAS_AUTH", "service_account").strip().lower() or "service_account",
        atlas_client_id=env.get("ATLAS_CLIENT_ID", "").strip(),
        atlas_client_secret=env.get("ATLAS_CLIENT_SECRET", "").strip(),
        atlas_public_key=env.get("ATLAS_PUBLIC_KEY", "").strip(),
        atlas_private_key=env.get("ATLAS_PRIVATE_KEY", "").strip(),
        atlas_items_per_page=int(env.get("ATLAS_ITEMS_PER_PAGE", "100")),
        atlas_timeout_seconds=float(env.get("ATLAS_TIMEOUT_SECONDS", "20")),
        atlas_max_retries=int(env.get("ATLAS_MAX_RETRIES", "4")),
        servicenow_instance_url=env.get("SERVICENOW_INSTANCE_URL", "").strip().rstrip("/"),
        servicenow_username=env.get("SERVICENOW_USERNAME", "").strip(),
        servicenow_password=env.get("SERVICENOW_PASSWORD", ""),
        servicenow_discovery_source=env.get("SERVICENOW_DISCOVERY_SOURCE", "atlas").strip(),
        servicenow_timeout_seconds=float(env.get("SERVICENOW_TIMEOUT_SECONDS", "20")),
        servicenow_max_retries=int(env.get("SERVICENOW_MAX_RETRIES", "3")),
        servicenow_allow_writes=_bool(env.get("SERVICENOW_ALLOW_WRITES", "false")),
    )


@dataclass
class ClassMapping:
    resource: str
    ci_class: str
    parent: str | None
    fallback_parent: str | None
    relationship_type: str | None
    attributes: dict = field(default_factory=dict)


@dataclass
class MappingConfig:
    discovery_source: str
    source_feed: str
    classes: dict
    attributes: dict

    def class_mapping(self, resource: str) -> ClassMapping:
        cls = self.classes[resource]
        return ClassMapping(
            resource=resource,
            ci_class=cls["class"],
            parent=cls.get("parent"),
            fallback_parent=cls.get("fallback_parent"),
            relationship_type=cls.get("relationship_type"),
            attributes=dict(self.attributes.get(resource, {})),
        )


def load_mapping(path: str) -> MappingConfig:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return MappingConfig(
        discovery_source=raw["discovery_source"],
        source_feed=raw["source_feed"],
        classes=raw["classes"],
        attributes=raw["attributes"],
    )
