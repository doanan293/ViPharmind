from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from pharma_lab import hashing
from pharma_lab.integrations.kaggle.artifacts import sha256_file
from pharma_lab.integrations.kaggle.config import OwnerConfiguration
from pharma_lab.integrations.kaggle.dataset_service import (
    DatasetInventory,
    DatasetPresence,
    DatasetService,
)
from pharma_lab.integrations.kaggle.model_artifacts import (
    CanonicalModelArtifact,
    resolve_publishable_artifact,
    stage_model_dataset,
)
from pharma_lab.integrations.kaggle.models import (
    ActionVerb,
    InputFile,
    ReconcileAction,
    StageJob,
)
from pharma_lab.integrations.kaggle.reconcile import DesiredDataset, plan_dataset

DesiredBuilder = Callable[
    [StageJob, OwnerConfiguration, Path], Sequence[DesiredDataset]
]


def static_keys(job: StageJob) -> frozenset[str]:
    """Input files that do not depend on the job (an e2e run's corpus and golden set)
    and so live in one dataset that every shard of the run mounts."""
    raw = job.worker_config.get("static_input_keys")
    return frozenset(str(key) for key in raw) if isinstance(raw, list) else frozenset()


def _static_files(job: StageJob) -> tuple[InputFile, ...]:
    keys = static_keys(job)
    return tuple(item for item in job.input_bundle.files if item.key in keys)


def _dynamic_files(job: StageJob) -> tuple[InputFile, ...]:
    keys = static_keys(job)
    return tuple(item for item in job.input_bundle.files if item.key not in keys)


def _static_fingerprint(job: StageJob) -> str:
    return hashing.canonical_sha256(
        {
            "schema_version": 1,
            "files": {item.key: item.descriptor() for item in _static_files(job)},
        }
    )


def input_dataset_slug(job: StageJob) -> str:
    return f"pipeline-input-{job.identity.sha256[:16]}"


def static_dataset_slug(job: StageJob) -> str:
    """Depends only on the content of the static files, never on the job."""
    return f"pipeline-static-{_static_fingerprint(job)[:16]}"


def kaggle_input_roots(job: StageJob) -> Mapping[str, Path]:
    """Where each input file is mounted in the kernel."""
    keys = static_keys(job)
    root = Path("/kaggle/input")
    return {
        item.key: root
        / (static_dataset_slug(job) if item.key in keys else input_dataset_slug(job))
        for item in job.input_bundle.files
    }


class DependencyService:
    def __init__(
        self,
        datasets: DatasetService,
        desired_builder: DesiredBuilder,
        *,
        publishers: Sequence[DatasetService] = (),
    ):
        self.datasets = datasets
        self.desired_builder = desired_builder
        # A dataset can only be created, versioned or verified as missing by the account
        # that owns it, so each reference goes through the profile that owns it.
        self.publishers: dict[str, DatasetService] = {
            service.owner.casefold(): service for service in publishers
        }
        self.publishers[datasets.owner.casefold()] = datasets

    def desired(
        self, job: StageJob, owners: OwnerConfiguration, workspace: Path
    ) -> Sequence[DesiredDataset]:
        return self.desired_builder(job, owners, workspace)

    def require_ready(self, reference: str) -> None:
        self.datasets.require_ready(
            reference,
            guidance="publish the Kaggle runtime dataset before running a stage",
        )

    def _owning_service(self, reference: str) -> DatasetService | None:
        owner, _, _slug = reference.partition("/")
        return self.publishers.get(owner.casefold())

    def _inventory(
        self, desired: Sequence[DesiredDataset], owners: OwnerConfiguration
    ) -> DatasetInventory:
        """Remote state of every desired dataset, read by the account that owns it.

        Another account cannot tell a missing dataset from one it may not see, so only
        references without an owning profile are read with the execution account.
        """
        states = {}
        for item in desired:
            service = self._owning_service(item.reference)
            reader, active_owner = (
                (service, service.owner)
                if service is not None
                else (self.datasets, owners.execution)
            )
            states.update(
                DatasetInventory.load(
                    reader,
                    {item.reference: item.manifest_filename},
                    active_owner=active_owner,
                ).states
            )
        return DatasetInventory(self.datasets, owners.execution, states)

    def reconcile(
        self,
        job: StageJob,
        owners: OwnerConfiguration,
        workspace: Path,
        *,
        force: bool,
        check_only: bool,
    ) -> Sequence[ReconcileAction]:
        desired = tuple(self.desired(job, owners, workspace))
        inventory = self._inventory(desired, owners)
        actions: list[ReconcileAction] = []
        for item in desired:
            _owner, _, slug = item.reference.partition("/")
            publisher = self._owning_service(item.reference)
            if (
                publisher is None
                and inventory.get(item.reference).presence is DatasetPresence.UNKNOWN
            ):
                raise ValueError(
                    f"No Kaggle account profile can publish {item.reference}; "
                    f"profiles own: {', '.join(sorted(self.publishers))}"
                )
            item_force = force and publisher is not None
            action = plan_dataset(item, inventory.get(item.reference), force=item_force)
            if action.verb is ActionVerb.WAIT and not check_only:
                reader = publisher or self.datasets
                reader.wait_for_dataset_ready(item.reference)
                refreshed = reader.inspect_state(
                    item.reference, active_owner=reader.owner
                )
                inventory.remember(item.reference, refreshed)
                action = plan_dataset(item, refreshed, force=item_force)
            if action.verb in {ActionVerb.CREATE, ActionVerb.UPDATE} and not check_only:
                if publisher is None:
                    raise ValueError(
                        f"No Kaggle account profile can publish {item.reference}; "
                        f"profiles own: {', '.join(sorted(self.publishers))}"
                    )
                with tempfile.TemporaryDirectory(
                    prefix=f"dependency-{item.resource_kind}-"
                ) as raw:
                    staged = item.materialize(Path(raw))
                    prepared = publisher.ensure_dataset(
                        slug,
                        item.title,
                        staged,
                        public=item.public,
                        active_owner=publisher.owner,
                    )
                publisher.wait_for_dataset_ready(
                    item.reference, minimum_version=prepared.expected_version
                )
                inventory.remember(
                    item.reference,
                    publisher.inspect_state(
                        item.reference, active_owner=publisher.owner
                    ),
                )
            actions.append(action)
        return actions


def _model_dataset(
    model: CanonicalModelArtifact, name: str, kind: str, owner: str
) -> DesiredDataset:
    def materialize(root: Path) -> Path:
        return stage_model_dataset(model, root, owner)

    return DesiredDataset(
        kind,
        f"{owner}/{model.dataset_slug}",
        f"Kaggle Pipeline Model {name}"[:50],
        model.sha256,
        "model_manifest.json",
        True,
        materialize,
    )


def default_desired_datasets(
    job: StageJob, owners: OwnerConfiguration, workspace: Path
) -> Sequence[DesiredDataset]:
    """Build the model and immutable input datasets consumed by a stage."""
    gguf_root_value = job.worker_config.get("gguf_root")
    if not isinstance(gguf_root_value, str) or not gguf_root_value:
        raise ValueError("stage job is missing gguf_root for model reconciliation")
    model_owner = owners.runtime or owners.execution
    # A kernel that runs several models (e2e) lists them; the others run job.model.
    raw_models = job.worker_config.get("models")
    names = (
        [str(name) for name in raw_models]
        if isinstance(raw_models, list)
        else [job.model]
    )
    model_datasets = [
        _model_dataset(
            resolve_publishable_artifact(Path(gguf_root_value), name),
            name,
            "model" if index == 0 else f"model-{index}",
            model_owner,
        )
        for index, name in enumerate(names)
    ]

    # Inputs hold evaluation questions and corpus text, so they stay private with the
    # account that runs the kernel; a session on another account uploads its own copy.
    inputs = [
        _input_dataset(
            "input",
            f"{owners.execution}/{input_dataset_slug(job)}",
            f"Kaggle Pipeline Input {job.stage.value}",
            job.input_bundle.sha256
            if not static_keys(job)
            else _dynamic_fingerprint(job),
            _dynamic_files(job),
        )
    ]
    if static_keys(job):
        inputs.insert(
            0,
            _input_dataset(
                "static",
                f"{owners.execution}/{static_dataset_slug(job)}",
                f"Kaggle Pipeline Static {job.stage.value}",
                _static_fingerprint(job),
                _static_files(job),
            ),
        )
    return (*model_datasets, *inputs, *_credentials(job, owners))


def _dynamic_fingerprint(job: StageJob) -> str:
    return hashing.canonical_sha256(
        {
            "schema_version": 1,
            "files": {item.key: item.descriptor() for item in _dynamic_files(job)},
        }
    )


def _input_dataset(
    kind: str,
    reference: str,
    title: str,
    fingerprint: str,
    files: Sequence[InputFile],
) -> DesiredDataset:
    def materialize(root: Path) -> Path:
        target = Path(root)
        target.mkdir(parents=True, exist_ok=True)
        for input_file in files:
            actual_digest = sha256_file(input_file.source_path)
            if actual_digest != input_file.sha256:
                raise ValueError(
                    f"Input bundle file changed for {input_file.key}: "
                    f"{actual_digest} != {input_file.sha256}"
                )
            shutil.copy2(input_file.source_path, target / input_file.filename)
        (target / "dependency_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "resource_kind": kind,
                    "fingerprint": fingerprint,
                    "files": {item.key: item.descriptor() for item in files},
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return target

    return DesiredDataset(
        kind,
        reference,
        title[:50],
        fingerprint,
        "dependency_manifest.json",
        False,
        materialize,
    )


def _credentials(
    job: StageJob, owners: OwnerConfiguration
) -> tuple[DesiredDataset, ...]:
    """The run's private credential dataset, when the job carries one (opt-in, e2e only).

    The manifest holds file names and the digest, never contents; the dataset is deleted
    by the command that created it."""
    local = job.worker_config.get("local_credentials_dir")
    slug = job.worker_config.get("credentials_slug")
    digest = job.worker_config.get("credentials_sha256")
    if not (
        isinstance(local, str) and isinstance(slug, str) and isinstance(digest, str)
    ):
        return ()

    def materialize(root: Path) -> Path:
        target = Path(root)
        target.mkdir(parents=True, exist_ok=True)
        names = []
        for path in sorted(Path(local).iterdir()):
            if path.is_file():
                shutil.copyfile(path, target / path.name)
                names.append(path.name)
        (target / "dependency_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "resource_kind": "credentials",
                    "fingerprint": digest,
                    "files": names,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return target

    return (
        DesiredDataset(
            "credentials",
            f"{owners.execution}/{slug}",
            "Kaggle Pipeline Run Auth",
            digest,
            "dependency_manifest.json",
            False,
            materialize,
        ),
    )
