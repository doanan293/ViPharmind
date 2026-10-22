import json
import zipfile
from dataclasses import replace
from pathlib import Path

from tests.integrations.kaggle.factories import (
    UnusedKernelService,
    rerank_runtime_profile,
    stage_request,
)

from pharma_lab.integrations.kaggle.api import kernel_output_command
from pharma_lab.integrations.kaggle.dependencies import input_dataset_slug
from pharma_lab.integrations.kaggle.kernels import PipelineKernelService
from pharma_lab.integrations.kaggle.models import (
    KernelPresence,
    KernelRemoteState,
    KernelStatus,
    StageName,
)
from pharma_lab.integrations.kaggle.stages import RerankStage


def test_kernel_output_downloads_diagnostic_sidecars(tmp_path):
    command = kernel_output_command("owner/kernel", tmp_path)

    assert command[-1] == r".*(jsonl|json|zip|tar|md|log)$"


def test_prepare_bundle_serializes_mounted_input_descriptors(tmp_path):
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
    (tmp_path / "manifest.json").write_text(
        json.dumps({"schema_version": 1}) + "\n", encoding="utf-8"
    )
    job = RerankStage().build_job(
        stage_request(
            StageName.RERANK,
            "qwen3-reranker:0.6b-q8_0",
            candidates,
            runtime_profile=rerank_runtime_profile(),
        )
    )

    bundle = PipelineKernelService(
        service=UnusedKernelService(), owner="owner", source_root=Path("src")
    ).prepare_bundle(
        job,
        root=tmp_path / "bundle",
        dataset_references=["owner/runtime"],
        checkpoint_reference="secondary-user/checkpoint-slug",
        total_budget_seconds=60,
    )
    config = json.loads((bundle / "stage_config.json").read_text(encoding="utf-8"))
    metadata = json.loads((bundle / "kernel-metadata.json").read_text(encoding="utf-8"))
    mounted_root = Path("/kaggle/input") / input_dataset_slug(job)

    assert config["input_files"] == {
        key: {
            "path": str(mounted_root / descriptor["filename"]),
            "filename": descriptor["filename"],
            "sha256": descriptor["sha256"],
        }
        for key, descriptor in job.input_bundle.descriptors().items()
    }
    assert "candidate_path" not in config
    assert "candidate_manifest_path" not in config
    assert "secondary-user/checkpoint-slug" in metadata["dataset_sources"]
    assert "owner/checkpoint-slug" not in metadata["dataset_sources"]


def test_kernel_reference_uses_sixteen_identity_characters(tmp_path):
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
    (tmp_path / "manifest.json").write_text("{}\n", encoding="utf-8")
    job = RerankStage().build_job(
        stage_request(
            StageName.RERANK,
            "qwen3-reranker:0.6b-q8_0",
            candidates,
            runtime_profile=rerank_runtime_profile(),
        )
    )

    service = PipelineKernelService(
        service=UnusedKernelService(), owner="owner", source_root=Path("src")
    )

    assert service.reference(job) == f"owner/rerank-{job.identity.sha256[:16]}"
    assert not hasattr(service, "references")


def test_discover_reports_absent_when_the_kernel_is_confirmed_missing(tmp_path):
    candidates = tmp_path / "candidates.jsonl"
    candidates.write_text(
        json.dumps(
            {"query_id": "q1", "query": "query", "candidates": [{"chunk_id": "c1"}]}
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text("{}\n", encoding="utf-8")
    job = RerankStage().build_job(
        stage_request(
            StageName.RERANK,
            "qwen3-reranker:0.6b-q8_0",
            candidates,
            runtime_profile=rerank_runtime_profile(),
        )
    )

    class FakeKernelService(UnusedKernelService):
        def __init__(self):
            self.checked = []

        def inspect_state(self, reference: str) -> KernelRemoteState:
            self.checked.append(reference)
            if reference.endswith(job.identity.sha256[:16]):
                return KernelRemoteState(
                    reference,
                    KernelPresence.UNKNOWN,
                    detail="Permission 'kernels.get' was denied",
                )
            return KernelRemoteState(
                reference, KernelPresence.EXISTS, KernelStatus.RUNNING
            )

        def confirm_missing(self, reference: str) -> bool | None:
            assert reference.endswith(job.identity.sha256[:16])
            return True

    fake = FakeKernelService()
    service = PipelineKernelService(fake, owner="owner", source_root=Path("src"))

    state = service.discover(job)

    assert state.presence is KernelPresence.ABSENT
    assert state.reference == service.reference(job)
    assert fake.checked == [service.reference(job)]


def _bundle_names(tmp_path: Path, *, bundle_backend: bool) -> set[str]:
    lab = tmp_path / "lab"
    (lab / "pharma_lab").mkdir(parents=True)
    (lab / "pharma_lab/__init__.py").write_text("", encoding="utf-8")
    backend = tmp_path / "backend"
    migrations = backend / "pharma_agent/migrations"
    migrations.mkdir(parents=True)
    (backend / "pharma_agent/__init__.py").write_text("", encoding="utf-8")
    (migrations / "script.py.mako").write_text("", encoding="utf-8")
    (backend / "pharma_agent/__pycache__").mkdir()
    (backend / "pharma_agent/__pycache__/x.pyc").write_bytes(b"")
    candidates = tmp_path / "candidates.jsonl"
    candidates.write_text(
        json.dumps(
            {
                "query_id": "q1",
                "query": "q",
                "candidates": [{"chunk_id": "c1", "document_text": "t"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text("{}\n", encoding="utf-8")
    job = RerankStage().build_job(
        stage_request(
            StageName.RERANK,
            "qwen3-reranker:0.6b-q8_0",
            candidates,
            runtime_profile=rerank_runtime_profile(),
        )
    )
    job = replace(
        job, worker_config=job.worker_config | {"bundle_backend": bundle_backend}
    )
    bundle = PipelineKernelService(
        service=UnusedKernelService(),
        owner="owner",
        source_root=lab,
        backend_source_root=backend,
    ).prepare_bundle(
        job,
        root=tmp_path / "bundle",
        dataset_references=[],
        checkpoint_reference=None,
        total_budget_seconds=60,
    )
    with zipfile.ZipFile(bundle / "source_bundle.zip") as archive:
        return set(archive.namelist())


def test_bundle_carries_the_backend_only_when_the_job_asks(tmp_path):
    with_backend = _bundle_names(tmp_path / "a", bundle_backend=True)
    without = _bundle_names(tmp_path / "b", bundle_backend=False)

    assert {
        "pharma_lab/__init__.py",
        "pharma_agent/__init__.py",
        "pharma_agent/migrations/script.py.mako",
    } <= with_backend
    assert not any("__pycache__" in name for name in with_backend)
    assert without == {"pharma_lab/__init__.py"}
