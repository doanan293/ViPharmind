import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.integrations.kaggle.factories import (
    job_identity,
    owners,
    rerank_runtime_profile,
    stage_job,
    stage_request,
)

from pharma_lab.integrations.kaggle import dependencies
from pharma_lab.integrations.kaggle.dataset_service import (
    DatasetPresence,
    DatasetRemoteState,
    DatasetService,
    PreparedDataset,
)
from pharma_lab.integrations.kaggle.models import (
    ActionVerb,
    InputBundle,
    InputFile,
    StageJob,
    StageName,
)
from pharma_lab.integrations.kaggle.reconcile import DesiredDataset
from pharma_lab.integrations.kaggle.stages import RerankStage


def _job(tmp_path: Path):
    candidates = tmp_path / "candidates.jsonl"
    candidates.write_text(
        json.dumps(
            {
                "query_id": "q1",
                "query": "query",
                "candidates": [{"chunk_id": "c1", "document_text": "text"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1}) + "\n", encoding="utf-8")
    request = stage_request(
        StageName.RERANK,
        "qwen3-reranker:0.6b-q8_0",
        candidates,
        runtime_profile=rerank_runtime_profile(),
    )
    return RerankStage().build_job(request), candidates, manifest


def test_input_dataset_materializes_every_bundle_file_and_manifest(
    tmp_path, monkeypatch
):
    job, candidates, manifest = _job(tmp_path)
    monkeypatch.setattr(
        dependencies,
        "resolve_publishable_artifact",
        lambda *_args: SimpleNamespace(
            dataset_slug="model",
            sha256="model-sha",
        ),
    )
    desired = dependencies.default_desired_datasets(job, owners(), tmp_path)
    input_dataset = next(item for item in desired if item.resource_kind == "input")
    staged = input_dataset.materialize(tmp_path / "staged")
    payload = json.loads(
        (staged / "dependency_manifest.json").read_text(encoding="utf-8")
    )

    assert input_dataset.fingerprint == job.input_bundle.sha256
    assert input_dataset.manifest_filename == "dependency_manifest.json"
    assert payload == {
        "schema_version": 2,
        "resource_kind": "input",
        "fingerprint": job.input_bundle.sha256,
        "files": job.input_bundle.descriptors(),
    }
    assert (staged / "candidates.jsonl").read_bytes() == candidates.read_bytes()
    assert (staged / "manifest.json").read_bytes() == manifest.read_bytes()


def test_desired_datasets_multi_owner_resolution(tmp_path, monkeypatch):
    job, _, _ = _job(tmp_path)
    monkeypatch.setattr(
        dependencies,
        "resolve_publishable_artifact",
        lambda *_args: SimpleNamespace(
            dataset_slug="model-slug",
            sha256="model-sha",
        ),
    )
    owner_configuration = owners(
        "worker-acc",
        runtime="runtime-acc",
        checkpoint="worker-acc",
    )
    desired = dependencies.default_desired_datasets(job, owner_configuration, tmp_path)
    by_kind = {item.resource_kind: item for item in desired}

    assert by_kind["model"].reference == "runtime-acc/model-slug"
    assert by_kind["model"].public is True
    # Inputs hold the evaluation questions and corpus text, so each account keeps its
    # own private copy; only the model, open weights, is public and shared.
    assert by_kind["input"].reference.startswith("worker-acc/pipeline-input-")
    assert by_kind["input"].public is False


def test_corpus_embed_input_is_a_pipeline_input_like_every_stage(tmp_path):
    job, _, _ = _job(tmp_path)
    corpus_embed = replace(job, stage=StageName.CORPUS_EMBED)

    assert dependencies.input_dataset_slug(
        corpus_embed
    ) == dependencies.input_dataset_slug(job)
    assert dependencies.input_dataset_slug(job).startswith("pipeline-input-")


def test_a_job_with_several_models_gets_one_model_dataset_each(tmp_path, monkeypatch):
    job, _, _ = _job(tmp_path)
    models = ["qwen3.5:9b-q8_0", "qwen3-reranker:4b-q8_0", "qwen3-embedding:4b-q8_0"]
    job = replace(job, worker_config=job.worker_config | {"models": models})
    monkeypatch.setattr(
        dependencies,
        "resolve_publishable_artifact",
        lambda _root, model: SimpleNamespace(
            dataset_slug=f"slug-{model}", sha256=f"sha-{model}"
        ),
    )

    desired = dependencies.default_desired_datasets(job, owners("acc"), tmp_path)

    assert [item.resource_kind for item in desired] == [
        "model",
        "model-1",
        "model-2",
        "input",
    ]
    assert [item.reference for item in desired[:3]] == [
        f"acc/slug-{model}" for model in models
    ]


class UnusedRunner:
    def run(
        self,
        args: list[str],
        capture_output: bool = False,
        *,
        live_output: bool = False,
    ) -> str:
        raise AssertionError(f"unexpected Kaggle command: {args}")


class FakeKaggleDatasets:
    """Shared remote dataset state seen by every account's DatasetService."""

    def __init__(self, monkeypatch):
        self.monkeypatch = monkeypatch
        self.published: set[str] = set()
        self.created: list[tuple[str, str]] = []

    def service(self, owner: str) -> DatasetService:
        service = DatasetService(UnusedRunner(), owner)

        def inspect_state(reference, *, active_owner=None):
            if reference in self.published:
                return DatasetRemoteState(
                    DatasetPresence.EXISTS, status="READY", current_version=1
                )
            # Like Kaggle: another account cannot tell a missing dataset from a
            # private one it may not see.
            if not reference.startswith(f"{owner}/"):
                return DatasetRemoteState(
                    DatasetPresence.UNKNOWN,
                    detail=f"cannot verify optional dataset {reference}: owner differs",
                )
            return DatasetRemoteState(DatasetPresence.ABSENT)

        def ensure_dataset(
            slug, title, path, *, public=False, active_owner=None, message=None
        ):
            reference = f"{owner}/{slug}"
            self.created.append((owner, reference))
            self.published.add(reference)
            return PreparedDataset(reference, True, 1)

        def wait_for_dataset_ready(
            reference, *, minimum_version=None, max_attempts=300
        ):
            return None

        self.monkeypatch.setattr(service, "inspect_state", inspect_state)
        self.monkeypatch.setattr(service, "ensure_dataset", ensure_dataset)
        self.monkeypatch.setattr(
            service, "wait_for_dataset_ready", wait_for_dataset_ready
        )
        return service


def _shared_model(job: StageJob, owner_configuration, workspace: Path):
    del job, workspace
    return (
        DesiredDataset(
            "model",
            f"{owner_configuration.runtime}/model-slug",
            "Kaggle Pipeline Model",
            "model-sha",
            "model_manifest.json",
            True,
            lambda root: root,
        ),
    )


def test_missing_shared_dataset_is_created_by_the_shared_owner_profile(
    tmp_path, monkeypatch
):
    kaggle = FakeKaggleDatasets(monkeypatch)
    service = dependencies.DependencyService(
        kaggle.service("tertiary-user"),
        _shared_model,
        publishers=(kaggle.service("primary-user"),),
    )

    actions = service.reconcile(
        stage_job(tmp_path),
        owners("tertiary-user", runtime="primary-user"),
        tmp_path,
        force=False,
        check_only=False,
    )

    assert [action.verb for action in actions] == [ActionVerb.CREATE]
    assert kaggle.created == [("primary-user", "primary-user/model-slug")]


def test_missing_dataset_without_an_owning_profile_fails_before_upload(
    tmp_path, monkeypatch
):
    kaggle = FakeKaggleDatasets(monkeypatch)
    service = dependencies.DependencyService(
        kaggle.service("tertiary-user"), _shared_model
    )

    with pytest.raises(
        ValueError,
        match="No Kaggle account profile can publish primary-user/model-slug",
    ):
        service.reconcile(
            stage_job(tmp_path),
            owners("tertiary-user", runtime="primary-user"),
            tmp_path,
            force=False,
            check_only=False,
        )
    assert kaggle.created == []


def _two_shards(tmp_path: Path):
    """Two jobs of one run: the same corpus (static), a different job file (dynamic)."""
    jobs = []
    for index, name in enumerate(("a", "b")):
        root = tmp_path / name
        root.mkdir()
        corpus = root / "corpus.json"
        corpus.write_text('{"chunks": 3}\n', encoding="utf-8")
        shard = root / "job.json"
        shard.write_text(json.dumps({"items": [index]}) + "\n", encoding="utf-8")
        bundle = InputBundle.create(
            (InputFile.create("corpus", corpus), InputFile.create("job", shard))
        )
        base = stage_job(root, stage=StageName.E2E_RUN)
        jobs.append(
            replace(
                base,
                input_bundle=bundle,
                identity=job_identity(
                    StageName.E2E_RUN, base.model, input_sha256=bundle.sha256
                ),
                worker_config={
                    "gguf_root": str(tmp_path),
                    "static_input_keys": ["corpus"],
                },
            )
        )
    return jobs


def _patch_model(monkeypatch) -> None:
    monkeypatch.setattr(
        dependencies,
        "resolve_publishable_artifact",
        lambda *_args: SimpleNamespace(dataset_slug="model", sha256="model-sha"),
    )


def test_two_shards_of_one_run_share_the_static_dataset(tmp_path, monkeypatch):
    _patch_model(monkeypatch)
    first, second = _two_shards(tmp_path)

    one = {
        i.resource_kind: i
        for i in dependencies.default_desired_datasets(first, owners("acc"), tmp_path)
    }
    two = {
        i.resource_kind: i
        for i in dependencies.default_desired_datasets(second, owners("acc"), tmp_path)
    }

    assert one["static"].reference == two["static"].reference
    assert one["static"].reference.startswith("acc/pipeline-static-")
    assert one["input"].reference != two["input"].reference


def test_static_dataset_changes_when_the_corpus_changes(tmp_path, monkeypatch):
    _patch_model(monkeypatch)
    first, _ = _two_shards(tmp_path)
    before = dependencies.static_dataset_slug(first)
    source = first.input_bundle.file("corpus").source_path
    source.write_text('{"chunks": 4}\n', encoding="utf-8")
    rebuilt = replace(
        first,
        input_bundle=InputBundle.create(
            (InputFile.create("corpus", source), first.input_bundle.file("job"))
        ),
    )

    assert dependencies.static_dataset_slug(rebuilt) != before


def test_static_dataset_is_private_and_holds_only_static_files(tmp_path, monkeypatch):
    _patch_model(monkeypatch)
    first, _ = _two_shards(tmp_path)
    desired = {
        i.resource_kind: i
        for i in dependencies.default_desired_datasets(first, owners("acc"), tmp_path)
    }

    static = desired["static"].materialize(tmp_path / "static")
    dynamic = desired["input"].materialize(tmp_path / "dynamic")

    assert desired["static"].public is False
    assert sorted(p.name for p in static.iterdir()) == [
        "corpus.json",
        "dependency_manifest.json",
    ]
    assert sorted(p.name for p in dynamic.iterdir()) == [
        "dependency_manifest.json",
        "job.json",
    ]


def test_input_roots_map_each_file_to_its_dataset(tmp_path):
    first, _ = _two_shards(tmp_path)

    roots = dependencies.kaggle_input_roots(first)

    assert roots["corpus"] == Path("/kaggle/input") / dependencies.static_dataset_slug(
        first
    )
    assert roots["job"] == Path("/kaggle/input") / dependencies.input_dataset_slug(
        first
    )


def test_existing_stages_still_get_one_input_dataset(tmp_path, monkeypatch):
    _patch_model(monkeypatch)
    job, _, _ = _job(tmp_path)

    desired = dependencies.default_desired_datasets(job, owners("acc"), tmp_path)

    assert [i.resource_kind for i in desired] == ["model", "input"]
    assert set(dependencies.kaggle_input_roots(job).values()) == {
        Path("/kaggle/input") / dependencies.input_dataset_slug(job)
    }


def test_credential_dataset_is_never_public(tmp_path, monkeypatch):
    _patch_model(monkeypatch)
    job, _, _ = _job(tmp_path)
    staged = tmp_path / "creds"
    staged.mkdir()
    (staged / "claude-a.json").write_text(
        '{"type": "claude", "token": "SECRET-TOKEN"}', encoding="utf-8"
    )
    job = replace(
        job,
        worker_config=job.worker_config
        | {
            "local_credentials_dir": str(staged),
            "credentials_slug": "pipeline-cred-abc",
            "credentials_sha256": "f" * 64,
        },
    )

    desired = {
        i.resource_kind: i
        for i in dependencies.default_desired_datasets(job, owners("acc"), tmp_path)
    }

    credentials = desired["credentials"]
    assert credentials.reference == "acc/pipeline-cred-abc"
    assert credentials.public is False
    assert credentials.fingerprint == "f" * 64
    copied = credentials.materialize(tmp_path / "up")
    assert sorted(p.name for p in copied.iterdir()) == [
        "claude-a.json",
        "dependency_manifest.json",
    ]
    manifest = json.loads((copied / "dependency_manifest.json").read_text())
    assert manifest["files"] == ["claude-a.json"]
    assert "SECRET-TOKEN" not in json.dumps(manifest)


def test_a_job_without_credentials_gets_no_credential_dataset(tmp_path, monkeypatch):
    _patch_model(monkeypatch)
    job, _, _ = _job(tmp_path)

    desired = dependencies.default_desired_datasets(job, owners("acc"), tmp_path)

    assert "credentials" not in {i.resource_kind for i in desired}
