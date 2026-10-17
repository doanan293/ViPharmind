import json

import pytest

from pharma_lab.artifacts.manifest import (
    ArtifactContractError,
    ArtifactManifest,
    Completion,
    iter_jsonl_objects,
    load_manifest,
    sha256_file,
    validate_data_file,
    write_json,
)


def test_missing_file_is_a_contract_error(tmp_path):
    with pytest.raises(ArtifactContractError, match="Cannot read artifact file"):
        sha256_file(tmp_path / "missing.jsonl")


def test_completion_rejects_counts_that_do_not_add_up():
    with pytest.raises(ArtifactContractError, match="complete \\+ missing == total"):
        Completion(total=3, complete=1, missing=1)
    assert Completion(total=2, complete=2, missing=0).is_complete


def test_manifest_round_trips_through_json_and_validates_its_data_file(tmp_path):
    data = tmp_path / "rows.jsonl"
    data.write_text('{"a": 1}\n\n{"a": 2}\n', encoding="utf-8")
    manifest = ArtifactManifest.create(
        artifact_type="demo", data_path=data, record_count=2, identity={"k": "v"}
    )
    write_json(tmp_path / "manifest.json", manifest.to_dict())

    loaded = load_manifest(tmp_path / "manifest.json")

    assert loaded == manifest
    assert validate_data_file(data, loaded) == 2
    assert [row["a"] for row in iter_jsonl_objects(data)] == [1, 2]


def test_non_object_jsonl_line_is_a_contract_error(tmp_path):
    data = tmp_path / "rows.jsonl"
    data.write_text(json.dumps([1, 2]) + "\n", encoding="utf-8")
    with pytest.raises(ArtifactContractError, match="must be a JSON object"):
        list(iter_jsonl_objects(data))
