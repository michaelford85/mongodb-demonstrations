"""Demo store for the operational change lifecycle: drafts, validation,
approval, versions, audit, and synthetic context/notes.

Two backends:
- MongoStore: uses the repo's established Atlas connection pattern (MONGODB_URI
  from .env, dedicated demo database, lazy connection). Only the collections
  in COLLECTIONS are touched.
- MemoryStore: fully local mock mode used when MONGODB_URI is empty, so the
  story can be rehearsed without any cluster. Clearly labeled as a mock.

Approval gating lives here, not in the agent: publishing requires an
approval record for the draft, whatever the backend.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from pymongo import MongoClient

from agent_change_ops_agent.evaluator import active_config_snapshot
from agent_change_ops_agent.fixtures import ALL_FIXTURES

logger = logging.getLogger(__name__)

DEMO_DATABASE_DEFAULT = "change_ops_demo"
COLLECTIONS = {
    "drafts": "change_drafts",
    "configs": "config_versions",
    "approvals": "change_approvals",
    "audit": "change_audit",
    "context": "demo_context",
    "notes": "change_notes",
}

AUDIT_EVENTS = (
    "draft_created",
    "validation_passed",
    "validation_failed",
    "simulation_run",
    "approval_requested",
    "approval_granted",
    "approval_denied",
    "version_published",
    "version_superseded",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_document_sets() -> dict:
    """Return the synthetic context documents keyed by collection name."""
    return {
        "workspaces": [ALL_FIXTURES["workspace"]],
        "services": ALL_FIXTURES["services"],
        "tag_metadata": ALL_FIXTURES["tag_metadata"],
        "sample_cases": ALL_FIXTURES["sample_cases"],
    }


class BaseStore:
    """Shared lifecycle logic; subclasses provide the collection accessors."""

    mode = "abstract"

    # -- collection accessors (backend-specific) -----------------------------
    def _col(self, name: str):  # pragma: no cover - backend-specific
        raise NotImplementedError

    def _all(self, name: str, query: Optional[dict] = None) -> list:
        raise NotImplementedError

    def _insert(self, name: str, doc: dict) -> dict:
        raise NotImplementedError

    def _replace(self, name: str, query: dict, updates: dict) -> Optional[dict]:
        raise NotImplementedError

    def clear_demo_data(self) -> None:
        raise NotImplementedError

    # -- seeding --------------------------------------------------------------
    def ensure_seeded(self) -> None:
        """Insert synthetic fixtures (including the baseline active config)
        if the demo context is empty. Scoped strictly to demo collections."""
        if self._all("context", {"kind": "workspaces"}):
            return
        for kind, docs in _seed_document_sets().items():
            for doc in docs:
                record = {"kind": kind, "data": doc, "demo": True}
                record.update(doc)
                self._insert("context", record)
        for note in ALL_FIXTURES["change_notes"]:
            record = {"kind": "change_notes", "data": note, "demo": True}
            record.update(note)
            self._insert("notes", record)
        config_v1 = dict(ALL_FIXTURES["config_v1"])
        self._insert("configs", config_v1)
        logger.info("Seeded synthetic operational-change demo fixtures (fictional data)")

    # -- context retrieval (explicit tools for the agent) --------------------
    def get_workspace(self, workspace_id: str) -> Optional[dict]:
        return self._one("context", {"kind": "workspaces", "workspace_id": workspace_id})

    def list_services(self, workspace_id: str) -> list:
        return self._all("context", {"kind": "services", "workspace_id": workspace_id})

    def list_tag_metadata(self, workspace_id: str) -> list:
        return self._all("context", {"kind": "tag_metadata", "workspace_id": workspace_id})

    def list_sample_cases(self) -> list:
        return self._all("context", {"kind": "sample_cases"})

    def list_catalog(self, kind: str) -> list:
        """List context records of a given kind ('services', 'tag_metadata', ...)."""
        return self._all("context", {"kind": kind})

    def list_notes(self) -> list:
        return self._all("notes")

    def keyword_search_notes(self, query: str) -> list:
        """Deterministic keyword fallback used when vector search is unavailable."""
        terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2]
        scored = []
        for doc in self._all("notes"):
            text = " ".join(
                str(doc.get(field, "")) for field in ("title", "note_text")
            ).lower()
            hits = sum(1 for term in terms if term in text)
            if hits:
                scored.append({"hits": hits, "doc": doc})
        scored.sort(key=lambda item: (-item["hits"], item["doc"].get("note_id", "")))
        return [item["doc"] for item in scored]

    def vector_search_notes(self, query: str, limit: int = 3) -> Optional[list]:
        """Semantic retrieval over change notes via Atlas Automated Embedding.

        Returns None when the vector path is unavailable (mock mode, missing
        index, or driver error), so callers can fall back to keyword search.
        """
        return None

    # -- config versions -------------------------------------------------------
    def list_configs(self) -> list:
        return self._all("configs")

    def get_active_config(self) -> Optional[dict]:
        return active_config_snapshot(self.list_configs())

    def save_draft(self, draft: dict) -> dict:
        doc = dict(draft)
        doc.setdefault("status", "draft")
        doc["created_at"] = _now()
        self._insert("drafts", doc)
        self.audit("draft_created", {"draft_id": doc["draft_id"]})
        return doc

    def get_draft(self, draft_id: str) -> Optional[dict]:
        return self._one("drafts", {"draft_id": draft_id})

    def update_draft(self, draft_id: str, updates: dict) -> Optional[dict]:
        return self._replace("drafts", {"draft_id": draft_id}, {**updates, "draft_id": draft_id})

    # -- approvals -------------------------------------------------------------
    def request_approval(self, draft_id: str, summary: str) -> dict:
        draft = self.get_draft(draft_id)
        if not draft:
            raise ValueError(f"Unknown draft: {draft_id}")
        if draft.get("status") not in ("draft", "pending_approval"):
            raise ValueError(
                f"Draft {draft_id} is {draft.get('status')!r}; "
                "only draft configurations can be submitted for approval"
            )
        approval = {
            "approval_id": f"apr-{draft_id}",
            "draft_id": draft_id,
            "decision": None,
            "summary": summary,
            "requested_at": _now(),
            "decided_at": None,
            "approver": None,
            "notes": None,
        }
        existing = self._one("approvals", {"draft_id": draft_id})
        if not existing:
            self._insert("approvals", approval)
        self._replace("drafts", {"draft_id": draft_id}, {"status": "pending_approval"})
        self.audit("approval_requested", {"draft_id": draft_id, "summary": summary})
        return approval

    def record_approval(self, draft_id: str, decision: str, approver: str, notes: str = "") -> dict:
        if decision not in ("approved", "denied"):
            raise ValueError("decision must be 'approved' or 'denied'")
        draft = self.get_draft(draft_id)
        if not draft:
            raise ValueError(f"Unknown draft: {draft_id}")
        if draft.get("status") != "pending_approval":
            raise ValueError(
                f"Draft {draft_id} is {draft.get('status')!r}; "
                "only pending_approval drafts can be decided"
            )
        decided_at = _now()
        self._replace(
            "approvals",
            {"draft_id": draft_id},
            {
                "decision": decision,
                "decided_at": decided_at,
                "approver": approver,
                "notes": notes,
            },
        )
        event = "approval_granted" if decision == "approved" else "approval_denied"
        next_status = "pending_approval" if decision == "approved" else "rejected"
        self._replace("drafts", {"draft_id": draft_id}, {"status": next_status})
        self.audit(event, {"draft_id": draft_id, "approver": approver, "notes": notes})
        return self.get_approval(draft_id)

    def get_approval(self, draft_id: str) -> Optional[dict]:
        return self._one("approvals", {"draft_id": draft_id})

    # -- publishing (the hard approval boundary) --------------------------------
    def publish(self, draft_id: str) -> dict:
        """Publish an approved draft as a new active configuration version.

        Raises when there is no recorded 'approved' decision for the draft.
        """
        draft = self.get_draft(draft_id)
        if not draft:
            raise ValueError(f"Unknown draft: {draft_id}")
        if draft.get("status") == "active":
            raise ValueError(f"Draft {draft_id} is already active")
        if draft.get("status") == "rejected":
            raise ValueError(f"Draft {draft_id} was rejected by a reviewer and cannot be published")
        approval = self.get_approval(draft_id)
        if not approval or approval.get("decision") != "approved":
            raise ValueError(
                f"Draft {draft_id} has no recorded human approval; "
                "refusing to publish (approval boundary)"
            )
        if draft.get("status") != "pending_approval":
            raise ValueError(f"Draft {draft_id} is {draft.get('status')!r}; cannot publish")

        current = self.get_active_config()
        new_version = (current or {}).get("config_version", 0) + 1
        published = {
            "config_id": draft["config_id"],
            "config_version": new_version,
            "status": "active",
            "label": draft.get("label", ""),
            "directives": draft["directives"],
            "default_action": draft.get("default_action", "deny"),
            "rationale": draft.get("rationale", ""),
            "source_draft": draft_id,
            "approved_by": approval.get("approver"),
            "approval_id": approval.get("approval_id"),
            "created_at": _now(),
            "activated_at": _now(),
            "note": "Fictional demo configuration - synthetic data only",
        }
        if current:
            self._replace(
                "configs",
                {"config_id": current["config_id"], "config_version": current["config_version"]},
                {**current, "status": "superseded"},
            )
            self._insert("configs", published)
            self.audit(
                "version_superseded",
                {
                    "config_id": current["config_id"],
                    "config_version": current["config_version"],
                    "new_version": new_version,
                },
            )
        else:
            self._insert("configs", published)
        self._replace("drafts", {"draft_id": draft_id}, {"status": "active"})
        self.audit(
            "version_published",
            {
                "config_id": published["config_id"],
                "config_version": new_version,
                "source_draft": draft_id,
                "approved_by": approval.get("approver"),
            },
        )
        return published

    # -- audit -------------------------------------------------------------------
    def audit(self, event: str, details: dict) -> None:
        if event not in AUDIT_EVENTS:
            raise ValueError(f"Unknown audit event: {event}")
        self._insert("audit", {"event": event, "at": _now(), "details": details})

    def audit_trail(self) -> list:
        return self._all("audit")


class MemoryStore(BaseStore):
    """In-memory mock backend. Clearly labeled as a demo approximation."""

    mode = "mock"

    def __init__(self) -> None:
        self.mode_label = "MOCK (in-memory, no MongoDB configured)"
        self._data: dict[str, list[dict]] = {name: [] for name in COLLECTIONS.values()}

    def _col(self, name: str) -> list:
        return self._data[COLLECTIONS[name]]

    def _all(self, name: str, query: Optional[dict] = None) -> list:
        query = query or {}
        out = []
        for doc in self._col(name):
            if all(doc.get(k) == v for k, v in query.items()):
                out.append(dict(doc))
        return out

    def _one(self, name: str, query: dict) -> Optional[dict]:
        docs = self._all(name, query)
        return docs[0] if docs else None

    def _insert(self, name: str, doc: dict) -> dict:
        self._col(name).append(dict(doc))
        return doc

    def _replace(self, name: str, query: dict, updates: dict) -> Optional[dict]:
        col = self._col(name)
        for i, doc in enumerate(col):
            if all(doc.get(k) == v for k, v in query.items()):
                merged = {**doc, **updates}
                col[i] = merged
                return dict(merged)
        return None

    def clear_demo_data(self) -> None:
        for name in COLLECTIONS.values():
            self._data[name] = []


class MongoStore(BaseStore):
    """MongoDB backend using the repo's Atlas connection pattern.

    Lazy connection, fast timeouts, dedicated demo database, indexes created
    on first use. Mirrors the reference scaffold's approach.
    """

    mode = "mongodb"

    def __init__(self, mongodb_uri: str, database: str = DEMO_DATABASE_DEFAULT) -> None:
        self._uri = mongodb_uri
        self._database = database
        self._client: Optional[MongoClient] = None
        self._vector_index_checked = False
        self._vector_index_available = False

    def _connect(self):
        if self._client is None:
            self._client = MongoClient(
                self._uri,
                connectTimeoutMS=5000,
                serverSelectionTimeoutMS=5000,
                socketTimeoutMS=10000,
            )
            col = self._client[self._database][COLLECTIONS["drafts"]]
            col.create_index("draft_id", unique=True)
            self._client[self._database][COLLECTIONS["configs"]].create_index(
                [("config_id", 1), ("config_version", 1)], unique=True
            )
            self._client[self._database][COLLECTIONS["approvals"]].create_index("draft_id", unique=True)
            self._client[self._database][COLLECTIONS["notes"]].create_index("note_id", unique=True)
        return self._client

    def _col(self, name: str):
        client = self._connect()
        return client[self._database][COLLECTIONS[name]]

    def _all(self, name: str, query: Optional[dict] = None) -> list:
        docs = self._col(name).find(query or {}, {"_id": 0})
        return [dict(d) for d in docs]

    def _one(self, name: str, query: dict) -> Optional[dict]:
        doc = self._col(name).find_one(query, {"_id": 0})
        return dict(doc) if doc else None

    def _insert(self, name: str, doc: dict) -> dict:
        self._col(name).insert_one(dict(doc))
        return doc

    def _replace(self, name: str, query: dict, updates: dict) -> Optional[dict]:
        doc = self._col(name).find_one_and_update(query, {"$set": dict(updates)}, return_document=True)
        return dict(doc) if doc else None

    # -- optional semantic retrieval (Atlas Automated Embedding) ---------------
    def vector_search_notes(self, query: str, limit: int = 3) -> Optional[list]:
        """$vectorSearch over change_notes using an autoEmbed index.

        Atlas generates and manages the embeddings itself (query is TEXT, not a
        vector). Returns None when the path is unavailable so callers fall back
        to deterministic keyword search. Never mutates data or indexes here.
        """
        from agent_change_ops_agent.vector_search import vector_search_notes

        if not self._vector_index_checked:
            self._vector_index_available = self.has_vector_index()
            self._vector_index_checked = True
        if not self._vector_index_available:
            return None
        try:
            return vector_search_notes(
                self._connect(), self._database, COLLECTIONS["notes"], query, limit
            )
        except Exception as exc:  # noqa: BLE001 - demo: degrade to fallback
            logger.warning("Vector search failed (%s); falling back to keyword search", exc)
            return None

    def has_vector_index(self) -> bool:
        """True when the demo's autoEmbed Vector Search index exists."""
        from agent_change_ops_agent.vector_search import VECTOR_INDEX_NAME

        try:
            client = self._connect()
            names = {
                idx.get("name")
                for idx in client[self._database][COLLECTIONS["notes"]].list_search_indexes()
            }
            return VECTOR_INDEX_NAME in names
        except Exception as exc:  # noqa: BLE001 - demo: degrade to fallback
            logger.warning("Could not list search indexes (%s)", exc)
            return False

    def clear_demo_data(self) -> None:
        """Drop ONLY the demo collections in the demo database."""
        for collection_name in COLLECTIONS.values():
            self._connect()  # connect + create indexes once
            self._client[self._database][collection_name].drop()
        if self._client is not None:
            self._client.close()
            self._client = None
        self._vector_index_checked = False
        self._vector_index_available = False


def create_store(mongodb_uri: str, database: str = DEMO_DATABASE_DEFAULT) -> BaseStore:
    """Mongo backend when a URI is configured, in-memory mock otherwise."""
    if mongodb_uri:
        return MongoStore(mongodb_uri, database)
    logger.warning("MONGODB_URI is empty: using MOCK in-memory store (no data is persisted)")
    return MemoryStore()
