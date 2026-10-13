"""Route a tenant's query to the right index — the whole point of the demo.

A small tenant is served by the ONE shared flat index on the base collection,
scoped with a `tenant_id` pre-filter. A large tenant is served by its OWN HNSW
index, which lives on a per-tenant View, so no filter is needed. Same query
API (`$vectorSearch`) either way; only the target namespace and the pre-filter
change.
"""
from dataclasses import dataclass

from . import tenants
from .client import (
    get_db, get_collection, view_name,
    FLAT_INDEX, HNSW_INDEX, COLLECTION_NAME,
    EMBEDDING_FIELD, TENANT_FIELD, QUERY_LIMIT,
)


@dataclass
class Route:
    strategy: str        # "flat" or "hnsw"
    namespace: str       # collection or view name the query targets
    index: str           # the search index name on that namespace
    tenant_id: str


def route(tenant_id: str, profile: str) -> Route:
    """Decide which index serves this tenant, given the profile's split."""
    if tenants.is_large(profile, tenant_id):
        return Route("hnsw", view_name(tenant_id), HNSW_INDEX, tenant_id)
    return Route("flat", COLLECTION_NAME, FLAT_INDEX, tenant_id)


def build_pipeline(query_vector: list, r: Route, limit: int = QUERY_LIMIT,
                   num_candidates: int = None) -> list:
    """Build the $vectorSearch pipeline for a resolved route.

    Flat routes carry a tenant_id pre-filter; HNSW-on-view routes do not,
    because the view already contains only that tenant's documents.
    """
    stage = {
        "index": r.index,
        "path": EMBEDDING_FIELD,
        "queryVector": query_vector,
        "limit": limit,
    }
    if r.strategy == "flat":
        stage["filter"] = {TENANT_FIELD: {"$eq": r.tenant_id}}
    else:
        stage["numCandidates"] = num_candidates or limit * 20
    return [
        {"$vectorSearch": stage},
        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
        {"$project": {"_id": 0, "doc_id": 1, "tenant_id": 1,
                      "category": 1, "text": 1, "score": 1}},
    ]


def _target(r: Route):
    return get_collection() if r.strategy == "flat" else get_db()[r.namespace]


def run_query(query_vector: list, tenant_id: str, profile: str,
              limit: int = QUERY_LIMIT) -> tuple:
    """Route, run, and return (results, route) for a query vector."""
    r = route(tenant_id, profile)
    pipeline = build_pipeline(query_vector, r, limit)
    results = list(_target(r).aggregate(pipeline))
    return results, r
