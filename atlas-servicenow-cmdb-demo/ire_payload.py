def _recency(value: str) -> str:
    if not value:
        return ""
    return value.replace("T", " ").replace("Z", "").replace("+00:00", "")


def build_ire_payload(records, mapping) -> dict:
    items = []
    relations = []
    by_source_id = {r.source_id: r for r in records}
    for record in records:
        cls = mapping.class_mapping(record.record_type)
        values = {}
        for cmdb_field, attr_key in cls.attributes.items():
            if attr_key in record.attributes and record.attributes[attr_key] is not None:
                values[cmdb_field] = record.attributes[attr_key]
        items.append(
            {
                "className": record.ci_class,
                "internal_id": record.source_id,
                "values": values,
                "sys_object_source_info": {
                    "source_feed": mapping.source_feed,
                    "source_name": mapping.discovery_source,
                    "source_native_key": record.source_native_key,
                    "source_recency_timestamp": _recency(record.recency_timestamp),
                },
            }
        )
        parent = record.parent_source_id
        if parent is not None and parent in by_source_id:
            relations.append(
                {
                    "parent_id": parent,
                    "child_id": record.source_id,
                    "type": record.relationship_type,
                    "sys_rel_source_info": {
                        "source_name": mapping.discovery_source,
                        "source_feed": mapping.source_feed,
                    },
                }
            )
    return {"items": items, "relations": relations}
