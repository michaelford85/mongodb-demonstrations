from dataclasses import dataclass, field, asdict


@dataclass
class CIRecord:
    record_type: str
    source_id: str
    name: str
    ci_class: str
    parent_source_id: str | None
    relationship_type: str | None
    source_native_key: str
    recency_timestamp: str
    attributes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _first_region_config(cluster: dict) -> dict:
    for spec in cluster.get("replicationSpecs") or []:
        for config in spec.get("regionConfigs") or []:
            return config
    return {}


def _cluster_region_summary(cluster: dict) -> str:
    config = _first_region_config(cluster)
    provider = config.get("providerName") or "unknown-provider"
    region = config.get("regionName") or "unknown-region"
    electable = config.get("electableSpecs") or {}
    size = electable.get("instanceSize") or "unknown-size"
    return f"{provider}/{region}/{size}"


def normalize_organization(org: dict, mapping) -> CIRecord:
    cls = mapping.class_mapping("organization")
    return CIRecord(
        record_type="organization",
        source_id=f"atlas:org:{org['id']}",
        name=org.get("name") or org["id"],
        ci_class=cls.ci_class,
        parent_source_id=None,
        relationship_type=None,
        source_native_key=org["id"],
        recency_timestamp="",
        attributes={
            "name": org.get("name") or org["id"],
            "org_id": org["id"],
        },
    )


def normalize_project(project: dict, mapping) -> CIRecord:
    cls = mapping.class_mapping("project")
    return CIRecord(
        record_type="project",
        source_id=f"atlas:project:{project['id']}",
        name=project["name"],
        ci_class=cls.ci_class,
        parent_source_id=f"atlas:org:{project['orgId']}",
        relationship_type=cls.relationship_type,
        source_native_key=project["id"],
        recency_timestamp=project.get("created", ""),
        attributes={
            "name": project["name"],
            "org_id": project["orgId"],
            "created": project.get("created", ""),
            "cluster_count": project.get("clusterCount"),
            "description": f"MongoDB Atlas project {project['name']} ({project['id']})",
        },
    )


def normalize_cluster(cluster: dict, mapping) -> CIRecord:
    cls = mapping.class_mapping("cluster")
    conn = cluster.get("connectionStrings") or {}
    summary = _cluster_region_summary(cluster)
    return CIRecord(
        record_type="cluster",
        source_id=f"atlas:cluster:{cluster['id']}",
        name=cluster["name"],
        ci_class=cls.ci_class,
        parent_source_id=f"atlas:project:{cluster['groupId']}",
        relationship_type=cls.relationship_type,
        source_native_key=cluster["id"],
        recency_timestamp=cluster.get("createDate", ""),
        attributes={
            "name": cluster["name"],
            "cluster_id": cluster["id"],
            "cluster_type": cluster.get("clusterType", ""),
            "mongo_db_version": cluster.get("mongoDBVersion", ""),
            "mongo_db_major_version": cluster.get("mongoDBMajorVersion", ""),
            "state": cluster.get("stateName", ""),
            "paused": cluster.get("paused"),
            "backup_enabled": cluster.get("backupEnabled"),
            "connection_string_srv": conn.get("standardSrv", ""),
            "provider_region_size": summary,
            "create_date": cluster.get("createDate", ""),
            "description": (
                f"MongoDB Atlas {cluster.get('clusterType', '')} cluster "
                f"{cluster['name']} on {summary} (paused={cluster.get('paused')})"
            ),
        },
    )


def _first_label(value: str) -> str:
    if not value:
        return ""
    host = value.rsplit(":", 1)[0] if ":" in value else value
    return host.split(".", 1)[0]


def _hostname_first_label(process: dict) -> str:
    for key in ("userAlias", "hostname", "id"):
        label = _first_label(process.get(key) or "")
        if label:
            return label
    return ""


def match_cluster_for_process(process: dict, clusters: list) -> dict | None:
    label = _hostname_first_label(process)
    if not label:
        return None
    for cluster in clusters:
        name = cluster["name"]
        if label == name or label.startswith(f"{name}-"):
            return cluster
    return None


def normalize_process(process: dict, clusters: list, mapping) -> CIRecord:
    cls = mapping.class_mapping("process")
    cluster = match_cluster_for_process(process, clusters)
    if cluster is not None:
        parent_source_id = f"atlas:cluster:{cluster['id']}"
    else:
        parent_source_id = f"atlas:project:{process['groupId']}"
    name = process.get("userAlias") or process.get("id")
    return CIRecord(
        record_type="process",
        source_id=f"atlas:process:{process['groupId']}:{process['id']}",
        name=name,
        ci_class=cls.ci_class,
        parent_source_id=parent_source_id,
        relationship_type=cls.relationship_type,
        source_native_key=process["id"],
        recency_timestamp=process.get("lastPing", ""),
        attributes={
            "name": name,
            "process_id": process["id"],
            "hostname": process.get("hostname", ""),
            "port": process.get("port"),
            "type_name": process.get("typeName", ""),
            "replica_set_name": process.get("replicaSetName", ""),
            "shard_name": process.get("shardName", ""),
            "mongo_db_version": process.get("version", ""),
            "created": process.get("created", ""),
            "last_ping": process.get("lastPing", ""),
            "parent_kind": "cluster" if cluster is not None else "project",
        },
    )


def normalize_inventory(client, mapping, limit: int | None = None) -> list:
    org = client.get_organization()
    records = [normalize_organization(org, mapping)]
    projects_seen = 0
    for project in client.iter_projects():
        if limit is not None and projects_seen >= limit:
            break
        records.append(normalize_project(project, mapping))
        clusters = list(client.iter_clusters(project["id"]))
        for cluster in clusters:
            records.append(normalize_cluster(cluster, mapping))
        for process in client.iter_processes(project["id"]):
            records.append(normalize_process(process, clusters, mapping))
        projects_seen += 1
    return records
