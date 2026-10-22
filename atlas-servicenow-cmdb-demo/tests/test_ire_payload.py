from ire_payload import build_ire_payload


def test_payload_structure(normalized, mapping):
    payload = build_ire_payload(normalized, mapping)
    assert set(payload) == {"items", "relations"}
    assert len(payload["items"]) == len(normalized)
    internal_ids = [i["internal_id"] for i in payload["items"]]
    assert len(internal_ids) == len(set(internal_ids))
    for item in payload["items"]:
        assert item["className"]
        assert isinstance(item["values"], dict)
        assert set(item["sys_object_source_info"]) == {
            "source_feed",
            "source_name",
            "source_native_key",
            "source_recency_timestamp",
        }


def test_payload_only_includes_mapped_attributes(normalized, mapping):
    payload = build_ire_payload(normalized, mapping)
    by_internal = {i["internal_id"]: i for i in payload["items"]}
    cluster_item = next(i for i in payload["items"] if i["internal_id"].startswith("atlas:cluster:"))
    assert cluster_item["values"] == {
        "name": cluster_item["values"]["name"],
        "version": cluster_item["values"]["version"],
        "short_description": cluster_item["values"]["short_description"],
    }
    assert set(cluster_item["values"]) == {"name", "version", "short_description"}
    process_item = next(i for i in payload["items"] if i["internal_id"].startswith("atlas:process:"))
    assert set(process_item["values"]) == {"name", "version"}


def test_relations_use_internal_ids_and_configured_type(normalized, mapping):
    payload = build_ire_payload(normalized, mapping)
    ids = {i["internal_id"] for i in payload["items"]}
    assert len(payload["relations"]) == len(normalized) - 1
    for rel in payload["relations"]:
        assert rel["parent_id"] in ids
        assert rel["child_id"] in ids
        assert rel["type"] == "Contains::Contained by"
        assert rel["sys_rel_source_info"]["source_name"]
    parents = {rel["parent_id"] for rel in payload["relations"]}
    org_id = next(i["internal_id"] for i in payload["items"] if i["internal_id"].startswith("atlas:org:"))
    assert org_id in parents


def test_recency_timestamp_format(normalized, mapping):
    payload = build_ire_payload(normalized, mapping)
    process_item = next(i for i in payload["items"] if i["internal_id"].startswith("atlas:process:"))
    ts = process_item["sys_object_source_info"]["source_recency_timestamp"]
    assert "T" not in ts and "Z" not in ts
    assert ts.count(" ") == 1
