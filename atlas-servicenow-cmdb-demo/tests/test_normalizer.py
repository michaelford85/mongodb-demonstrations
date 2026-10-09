from normalizer import (
    match_cluster_for_process,
    normalize_cluster,
    normalize_inventory,
    normalize_process,
    normalize_project,
)


def by_type(records):
    out = {}
    for r in records:
        out.setdefault(r.record_type, []).append(r)
    return out


def test_source_ids_are_stable_and_namespaced(normalized):
    for r in normalized:
        assert r.source_id.startswith("atlas:")
        assert r.source_native_key
    org = by_type(normalized)["organization"][0]
    assert org.source_id == f"atlas:org:{org.source_native_key}"
    projects = by_type(normalized)["project"]
    assert projects[0].source_id == f"atlas:project:{projects[0].source_native_key}"


def test_parent_chain_org_to_project_to_cluster(normalized):
    groups = by_type(normalized)
    org = groups["organization"][0]
    for project in groups["project"]:
        assert project.parent_source_id == org.source_id
        assert project.relationship_type == "Contains::Contained by"
    for cluster in groups["cluster"]:
        project_ids = {p.source_id for p in groups["project"]}
        assert cluster.parent_source_id in project_ids
        assert cluster.attributes["mongo_db_version"]


def test_process_links_to_cluster_by_hostname_heuristic(normalized):
    groups = by_type(normalized)
    cluster_ids = {c.source_id for c in groups["cluster"]}
    project_ids = {p.source_id for p in groups["project"]}
    linked_to_cluster = [r for r in groups["process"] if r.parent_source_id in cluster_ids]
    linked_to_project = [r for r in groups["process"] if r.parent_source_id in project_ids]
    assert len(linked_to_cluster) >= 10
    assert all(r.attributes["parent_kind"] == "cluster" for r in linked_to_cluster)
    assert len(linked_to_project) == 1
    orphan = linked_to_project[0]
    assert orphan.name.startswith("orphan-process")
    assert orphan.attributes["parent_kind"] == "project"
    for r in groups["process"]:
        assert r.parent_source_id in cluster_ids | project_ids


def test_match_cluster_for_process_prefers_user_alias():
    clusters = [
        {"id": "c1", "groupId": "g", "name": "mford-demo-cluster"},
    ]
    process = {
        "userAlias": "mford-demo-cluster-shard-00-00.qkqabf.mongodb.net:27017",
        "hostname": "atlas-115elk-shard-00-00.qkqabf.mongodb.net",
    }
    assert match_cluster_for_process(process, clusters)["id"] == "c1"


def test_match_cluster_for_process_uses_name_prefix():
    clusters = [
        {"id": "c1", "groupId": "g", "name": "demo-rs"},
        {"id": "c2", "groupId": "g", "name": "demo-sharded"},
    ]
    assert match_cluster_for_process({"hostname": "demo-rs-shard-00-00.x.mongodb.net"}, clusters)["id"] == "c1"
    assert match_cluster_for_process({"id": "demo-sharded-mongos-0.x.mongodb.net:27017"}, clusters)["id"] == "c2"
    assert match_cluster_for_process({"hostname": "unrelated.x.mongodb.net"}, clusters) is None


def test_cluster_attributes_come_from_verified_fields(mapping):
    cluster = {
        "id": "abc",
        "groupId": "g1",
        "name": "demo-rs",
        "clusterType": "REPLICASET",
        "mongoDBVersion": "8.0.4",
        "mongoDBMajorVersion": "8.0",
        "stateName": "IDLE",
        "createDate": "2026-01-01T00:00:00Z",
        "paused": False,
        "backupEnabled": True,
        "connectionStrings": {"standardSrv": "mongodb+srv://demo-rs.x.mongodb.net"},
        "replicationSpecs": [
            {"regionConfigs": [{"providerName": "AWS", "regionName": "US_EAST_1",
                                 "electableSpecs": {"instanceSize": "M30"}}]}
        ],
    }
    record = normalize_cluster(cluster, mapping)
    assert record.attributes["provider_region_size"] == "AWS/US_EAST_1/M30"
    assert record.attributes["connection_string_srv"] == "mongodb+srv://demo-rs.x.mongodb.net"
    assert record.attributes["state"] == "IDLE"
    unknown = dict(cluster, extra_unverified_field="x")
    record2 = normalize_cluster(unknown, mapping)
    assert "extra_unverified_field" not in record2.attributes


def test_project_attributes_use_verified_fields(mapping):
    project = {
        "id": "p1",
        "orgId": "o1",
        "name": "proj",
        "created": "2026-01-01T00:00:00Z",
        "clusterCount": 2,
    }
    record = normalize_project(project, mapping)
    assert record.attributes["cluster_count"] == 2
    assert record.parent_source_id == "atlas:org:o1"
