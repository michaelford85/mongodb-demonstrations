"""Unit tests for the DMS CDC transform and the ASP pipeline artifact.

Run:  pytest tests/ -q
No AWS, Atlas, or API credentials are required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from dms_transform import transform  # noqa: E402
from fixtures import control_message, dms_message, load_stage_artifacts  # noqa: E402


class TestSnapshotAndInsert:
    def test_load_maps_to_read_model(self):
        doc = transform(dms_message(1, "load"))
        assert doc["_id"] == "knowledge-items-1"
        assert doc["source_id"] == "1"
        assert doc["cdc_operation"] == "load"
        assert doc["_is_delete"] is False
        assert doc["title"].startswith("Resetting")
        assert "password" in doc["searchable_text"]
        assert doc["source_updated_at"].startswith("2026-10-22")

    def test_insert_equivalent_to_load(self):
        assert transform(dms_message(2, "insert"))["_id"] == "knowledge-items-2"


class TestUpdate:
    def test_update_carries_new_row_image(self):
        doc = transform(dms_message(3, "update", body="Revised walkthrough."))
        assert doc["cdc_operation"] == "update"
        assert doc["body"] == "Revised walkthrough."
        assert not doc["_is_delete"]


class TestDelete:
    def test_delete_becomes_deletion_marker(self):
        doc = transform(dms_message(2, "delete"))
        assert doc["_is_delete"] is True
        assert doc["_id"] == "knowledge-items-2"

    def test_delete_event_without_title_is_accepted(self):
        msg = dms_message(9, "delete")
        msg["data"] = {"id": 9}  # PK-only image (no REPLICA IDENTITY FULL)
        assert transform(msg)["_id"] == "knowledge-items-9"


class TestReplayedAndMalformed:
    def test_replayed_event_is_idempotent(self):
        msg = dms_message(4, "update")
        assert transform(msg) == transform(msg)

    @pytest.mark.parametrize(
        "bad",
        [
            control_message(),                       # DMS control record
            dms_message(5, "load") | {"metadata": {"record-type": "data", "operation": "purge", "table-name": "knowledge_items"}},  # unknown op
            dms_message(6, "insert") | {"metadata": {"record-type": "data", "operation": "insert", "table-name": "other_table"}},    # wrong table
            {"data": None, "metadata": {"record-type": "data", "operation": "insert", "table-name": "knowledge_items"}},             # no data
            {"data": {"title": "no id"}, "metadata": {"record-type": "data", "operation": "insert", "table-name": "knowledge_items"}},  # missing PK
            None,
            "not-a-dict",
        ],
    )
    def test_malformed_or_irrelevant_records(self, bad):
        assert transform(bad) is None


class TestPipelineArtifact:
    def test_pipeline_is_valid_json_with_expected_stages(self):
        a, b = load_stage_artifacts()
        # Processor A: kafka → staging (no $https).
        assert [next(iter(st)) for st in a["pipeline"]] == ["$source", "$match", "$set", "$project", "$merge"]
        # Processor B: change stream → voyage → read model.
        # NOTE: no $match before $https and no $$NOW anywhere — both trigger
        # ASP serialization/runtime bugs (see README known limitations).
        assert [next(iter(st)) for st in b["pipeline"]] == [
            "$source", "$set", "$https", "$set", "$project", "$merge",
        ]

    def test_https_stage_targets_voyage(self):
        _, b = load_stage_artifacts()
        pipeline = b
        https = next(s["$https"] for s in pipeline["pipeline"] if "$https" in s)
        assert https["method"] == "POST"
        assert https["onError"] == "dlq"
        new_root = https["payload"][0]["$replaceRoot"]["newRoot"]
        assert new_root["model"] == "voyage-4"
        assert new_root["input_type"] == "document"
        # Content-Type must come from the voyage-ai CONNECTION headers
        # (operator-level headers are unnecessary in the two-processor design).
        assert "headers" not in https
        for secret in ("Authorization", "Bearer", "sk-", "VOYAGE_API_KEY"):
            assert secret not in json.dumps(pipeline), "no secrets may be embedded in the pipeline file"

    def test_merge_is_delete_aware(self):
        _, b = load_stage_artifacts()
        merge = next(s["$merge"] for s in b["pipeline"] if "$merge" in s)
        assert merge["whenMatched"]["$cond"]["then"] == "delete"
        assert merge["whenMatched"]["$cond"]["else"] == "replace"
        assert merge["whenNotMatched"]["$cond"]["then"] == "discard"
        assert merge["whenNotMatched"]["$cond"]["else"] == "insert"
        assert merge["into"]["db"] == "enterprise_search_demo"

    def test_vector_index_dimensions_match_model(self):
        # The pipeline omits output_dimension (numeric literals break $https
        # EJSON serialization), so it relies on the model's default dimension.
        # Keep VOYAGE_DIMENSIONS (= the index numDimensions) at that default.
        _, b = load_stage_artifacts()
        pipeline_json = json.dumps(b["pipeline"])
        assert "output_dimension" not in pipeline_json
        assert "$$NOW" not in pipeline_json  # unavailable in ASP; corrupts $https
        index_script = (Path(__file__).parent.parent / "scripts" / "create_atlas_indexes.py").read_text()
        assert "VOYAGE_DIMENSIONS" in index_script
