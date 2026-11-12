"""Demo store for call-control policy lifecycle: drafts, validation, approval, versions, audit.

Two backends:
- MongoStore: uses the repo's established Atlas connection pattern (MONGODB_URI
  from .env, dedicated demo database, lazy connection).
- MemoryStore: fully local mock mode used when MONGODB_URI is empty, so the
  story can be rehearsed without any cluster. Clearly labeled as a mock.

Approval gating lives here, not in the agent: publishing requires an
approval record for the draft, whatever the backend.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from pymongo import MongoClient

from agent_call_policy_agent.evaluator import active_policy_snapshot
from agent_call_policy_agent.fixtures import ALL_FIXTURES

logger = logging.getLogger(__name__)

DEMO_DATABASE_DEFAULT = "call_policy_demo"
COLLECTIONS = {
    "drafts": "policy_drafts",
    "policies": "policy_versions",
    "approvals": "policy_approvals",
    "audit": "policy_audit",
    "context": "demo_context",
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
        "enterprises": [ALL_FIXTURES["enterprise"]],
        "carrier_relationships": ALL_FIXTURES["carrier_relationships"],
        "brand_metadata": ALL_FIXTURES["brand_metadata"],
        "sample_calls": ALL_FIXTURES["sample_calls"],
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

    def _replace(self, name: str, query: dict, doc: dict) -> Optional[dict]:
        raise NotImplementedError

    def clear_demo_data(self) -> None:
        raise NotImplementedError

    # -- seeding --------------------------------------------------------------
    def ensure_seeded(self) -> None:
        """Insert synthetic fixtures (including the baseline active policy)
        if the demo context is empty. Scoped strictly to demo collections."""
        if self._all("context", {"kind": "enterprises"}):
            return
        for kind, docs in _seed_document_sets().items():
            for doc in docs:
                record = {"kind": kind, "data": doc, "demo": True}
                record.update(doc)
                self._insert("context", record)
        policy_v1 = dict(ALL_FIXTURES["policy_v1"])
        self._insert("policies", policy_v1)
        logger.info("Seeded synthetic call-control demo fixtures (fictional data)")

    # -- context retrieval (explicit tools for the agent) --------------------
    def get_enterprise(self, enterprise_id: str) -> Optional[dict]:
        return self._one("context", {"kind": "enterprises", "enterprise_id": enterprise_id})

    def list_carrier_relationships(self, enterprise_id: str) -> list:
        return self._all("context", {"kind": "carrier_relationships", "enterprise_id": enterprise_id})

    def list_brand_metadata(self, enterprise_id: str) -> list:
        return self._all("context", {"kind": "brand_metadata", "enterprise_id": enterprise_id})

    def list_sample_calls(self) -> list:
        return self._all("context", {"kind": "sample_calls"})

    def list_catalog(self, kind: str) -> list:
        """List context records of a given kind ('enterprises', 'brand_metadata', ...)."""
        return self._all("context", {"kind": kind})

    # -- policy versions -------------------------------------------------------
    def list_policies(self) -> list:
        return self._all("policies")

    def get_active_policy(self) -> Optional[dict]:
        return active_policy_snapshot(self.list_policies())

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
                f"Draft {draft_id} is {draft.get('status')!r}; only draft policies can be submitted for approval"
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
                f"Draft {draft_id} is {draft.get('status')!r}; only pending_approval drafts can be decided"
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
        """Publish an approved draft as a new active policy version.

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

        current = self.get_active_policy()
        new_version = (current or {}).get("policy_version", 0) + 1
        published = {
            "policy_id": draft["policy_id"],
            "policy_version": new_version,
            "status": "active",
            "label": draft.get("label", ""),
            "rules": draft["rules"],
            "default_action": draft.get("default_action", "block"),
            "rationale": draft.get("rationale", ""),
            "source_draft": draft_id,
            "approved_by": approval.get("approver"),
            "approval_id": approval.get("approval_id"),
            "created_at": _now(),
            "activated_at": _now(),
            "note": "Fictional demo policy - synthetic data only",
        }
        if current:
            self._replace(
                "policies",
                {"policy_id": current["policy_id"], "policy_version": current["policy_version"]},
                {**current, "status": "superseded"},
            )
            self._insert("policies", published)
            self.audit(
                "version_superseded",
                {
                    "policy_id": current["policy_id"],
                    "policy_version": current["policy_version"],
                    "new_version": new_version,
                },
            )
        else:
            self._insert("policies", published)
        self._replace("drafts", {"draft_id": draft_id}, {"status": "active"})
        self.audit(
            "version_published",
            {
                "policy_id": published["policy_id"],
                "policy_version": new_version,
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
    on first use. Mirrors the scaffold's _LazyCollection approach.
    """

    mode = "mongodb"

    def __init__(self, mongodb_uri: str, database: str = DEMO_DATABASE_DEFAULT) -> None:
        self._uri = mongodb_uri
        self._database = database
        self._client: Optional[MongoClient] = None

    def _col(self, name: str):
        if self._client is None:
            self._client = MongoClient(
                self._uri,
                connectTimeoutMS=5000,
                serverSelectionTimeoutMS=5000,
                socketTimeoutMS=10000,
            )
            col = self._client[self._database][COLLECTIONS["drafts"]]
            col.create_index("draft_id", unique=True)
            self._client[self._database][COLLECTIONS["policies"]].create_index(
                [("policy_id", 1), ("policy_version", 1)], unique=True
            )
            self._client[self._database][COLLECTIONS["approvals"]].create_index("draft_id", unique=True)
        return self._client[self._database][COLLECTIONS[name]]

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
        doc = self._col(name).find_one_and_update(
            query, {"$set": dict(updates)}, return_document=True
        )
        return dict(doc) if doc else None

    def clear_demo_data(self) -> None:
        """Drop ONLY the demo collections in the demo database."""
        for name in COLLECTIONS.values():
            self._col(name).drop()
        if self._client is not None:
            self._client.close()
            self._client = None


def create_store(mongodb_uri: str, database: str = DEMO_DATABASE_DEFAULT) -> BaseStore:
    """Mongo backend when a URI is configured, in-memory mock otherwise."""
    if mongodb_uri:
        return MongoStore(mongodb_uri, database)
    logger.warning(
        "MONGODB_URI is empty: using MOCK in-memory store (no data is persisted)"
    )
    return MemoryStore()
