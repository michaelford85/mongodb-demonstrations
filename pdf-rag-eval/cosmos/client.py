"""Cosmos DB client and bulk-upsert helper.

The container is assumed to already exist with the vector policy applied
by ../cosmosdb-cluster-provisioning. We do not (and cannot) modify the
vector policy here — Cosmos forbids it once data lands.
"""
from __future__ import annotations

from azure.cosmos import CosmosClient, ContainerProxy, PartitionKey

from config import Settings


def get_container(settings: Settings) -> ContainerProxy:
    """Return a ContainerProxy ready for read/write against the demo container."""
    client = CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
    database = client.get_database_client(settings.cosmos_database)
    return database.get_container_client(settings.cosmos_container)


def ensure_container(settings: Settings) -> ContainerProxy:
    """Best-effort: confirm the container exists, otherwise instruct the user.

    We intentionally do NOT auto-create the container because creation with a
    vector policy must be done through Terraform (azapi) so the policy is set
    at creation time. A missing container means the user skipped the
    cosmosdb-cluster-provisioning step.
    """
    client = CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
    database = client.get_database_client(settings.cosmos_database)
    try:
        container = database.get_container_client(settings.cosmos_container)
        container.read()
    except Exception as exc:
        raise SystemExit(
            f"Cosmos container '{settings.cosmos_container}' not found in "
            f"database '{settings.cosmos_database}'. Provision it first with "
            "../cosmosdb-cluster-provisioning/setup.sh — the vector policy "
            "must be set at container creation time."
        ) from exc
    return container
