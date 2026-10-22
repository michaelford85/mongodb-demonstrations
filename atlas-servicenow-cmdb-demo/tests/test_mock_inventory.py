from collections import Counter

from mock_atlas import MockAtlasClient

PROCESS_FIELDS = {
    "id",
    "groupId",
    "hostname",
    "port",
    "userAlias",
    "typeName",
    "replicaSetName",
    "shardName",
    "version",
    "created",
    "lastPing",
}

CLUSTER_FIELDS = {
    "id",
    "groupId",
    "name",
    "clusterType",
    "mongoDBMajorVersion",
    "mongoDBVersion",
    "stateName",
    "createDate",
    "paused",
    "backupEnabled",
    "connectionStrings",
    "replicationSpecs",
}


def test_mock_client_exposes_org_projects_clusters_processes():
    client = MockAtlasClient()
    org = client.get_organization()
    assert org["id"] and org["name"]
    projects = list(client.iter_projects())
    assert len(projects) == 3
    for project in projects:
        clusters = list(client.iter_clusters(project["id"]))
        processes = list(client.iter_processes(project["id"]))
        assert clusters, f"project {project['name']} should have clusters"
        assert processes
        assert all(c["groupId"] == project["id"] for c in clusters)
        assert all(p["groupId"] == project["id"] for p in processes)


def test_fixture_fields_match_verified_api_schemas():
    client = MockAtlasClient()
    for project in client.iter_projects():
        for cluster in client.iter_clusters(project["id"]):
            assert CLUSTER_FIELDS.issubset(cluster.keys())
            conn = cluster["connectionStrings"]
            assert conn["standardSrv"].startswith("mongodb+srv://")
        for process in client.iter_processes(project["id"]):
            assert PROCESS_FIELDS.issubset(process.keys())
            assert process["typeName"] in {
                "REPLICA_PRIMARY",
                "REPLICA_SECONDARY",
                "RECOVERING",
                "SHARD_MONGOS",
                "SHARD_CONFIG",
                "SHARD_STANDALONE",
                "SHARD_PRIMARY",
                "SHARD_SECONDARY",
                "NO_DATA",
            }
            assert ":" in process["id"] and process["id"].endswith(str(process["port"]))


def test_fixture_data_is_synthetic():
    client = MockAtlasClient()
    ids = [c["id"] for p in client.iter_projects() for c in client.iter_clusters(p["id"])]
    ids += [p["id"] for p in client.iter_projects()]
    assert all(len(i) == 24 and all(ch in "0123456789abcdef" for ch in i) for i in ids)
    hostnames = [
        proc["hostname"] for p in client.iter_projects() for proc in client.iter_processes(p["id"])
    ]
    assert all(h.endswith(".dummy.mongodb.net") for h in hostnames)


def test_limit_caps_projects():
    from pathlib import Path

    from config import load_mapping
    from mock_atlas import MockAtlasClient
    from normalizer import normalize_inventory

    mapping = load_mapping(str(Path(__file__).resolve().parent.parent / "mapping.json"))
    client = MockAtlasClient()
    records = normalize_inventory(client, mapping, limit=1)
    counts = Counter(r.record_type for r in records)
    assert counts["project"] == 1
    assert counts["organization"] == 1
    assert counts["cluster"] == 2
    assert all(r.attributes.get("org_id") in (None, "5f0f1a2b3c4d5e6f7a8b9c0d") for r in records)
