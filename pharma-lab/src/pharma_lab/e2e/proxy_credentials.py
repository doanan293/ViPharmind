"""The machine side of running `cli-proxy-api` in a kernel: which credential files go up
and the private per-run dataset that carries them.

A credential file is read for one thing, its `type`. Contents never reach a log, the
repository, `data/` or the `data push` archive: the files are staged in a private
temporary directory outside the checkout, uploaded to a private dataset named after the
run and the account, and that dataset is deleted when the command ends, even on error.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from pharma_lab.e2e.proxy_kernel import CONFIG_NAME, without_forced_keys

DOCKER_VOLUME = "vipharmind_cli_proxy_auth"
DELETE_ATTEMPTS = 3
INVALID = "invalid"

Deleter = Callable[[str, str], None]


@dataclass(frozen=True)
class CredentialFile:
    name: str
    type: str
    size: int


def list_credentials(directory: Path) -> list[CredentialFile]:
    """The `*.json` files of `directory` with their `type`; nothing else is read."""
    files = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            kind = payload.get("type") if isinstance(payload, dict) else None
            kind = kind if isinstance(kind, str) and kind else INVALID
        except (OSError, ValueError):
            kind = INVALID
        files.append(CredentialFile(path.name, kind, path.stat().st_size))
    return files


def select_credentials(
    files: Sequence[CredentialFile],
    providers: frozenset[str],
    names: Sequence[str],
) -> list[CredentialFile]:
    """The files named by the user, or every file of a provider the preset needs."""
    if names:
        by_name = {file.name: file for file in files}
        missing = [name for name in names if name not in by_name]
        if missing:
            raise ValueError(f"no such credential file: {', '.join(missing)}")
        return [by_name[name] for name in names]
    chosen = [file for file in files if file.type in providers]
    if not chosen:
        raise ValueError(
            f"no credential file of type {', '.join(sorted(providers))} found"
        )
    return chosen


def export_credentials_from_volume(
    volume: str,
    target: Path,
    *,
    run: Callable[..., object] = subprocess.run,
) -> None:
    """Copy the `*.json` files of the Docker volume (mounted read-only) into `target`."""
    target.mkdir(parents=True, exist_ok=True)
    target.chmod(0o700)
    run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume}:/auth:ro",
            "-v",
            f"{target}:/out",
            "alpine",
            "sh",
            "-c",
            "cp /auth/*.json /out/ && chmod 600 /out/*.json",
        ],
        check=True,
    )


def _fingerprint(directory: Path, files: Sequence[CredentialFile]) -> str:
    digest = hashlib.sha256()
    for file in sorted(files, key=lambda item: item.name):
        digest.update(file.name.encode() + b"\0")
        digest.update((directory / file.name).read_bytes())
    return digest.hexdigest()


class CredentialDataset:
    """Stages the chosen files and deletes the dataset of every account that used them."""

    def __init__(
        self,
        source: Path,
        files: Sequence[CredentialFile],
        *,
        run_name: str,
        template: Path | None,
        deleter: Deleter,
        say: Callable[[str], None] = print,
        retry_pause: float = 5.0,
    ) -> None:
        self.files = tuple(files)
        self._source = source
        self._run_name = run_name
        self._template = template
        self._deleter = deleter
        self._say = say
        self._retry_pause = retry_pause
        self._used: list[tuple[str, str]] = []
        self._staging: Path | None = None
        self.fingerprint = _fingerprint(source, self.files)

    @property
    def stage_dir(self) -> Path:
        if self._staging is None:
            raise RuntimeError("the credential dataset is not open")
        return self._staging

    def slug(self, profile: str) -> str:
        """Stable per run and account, so a relaunched shard finds its dataset again."""
        seed = f"{self.fingerprint}:{self._run_name}:{profile}".encode()
        return f"pipeline-cred-{hashlib.sha256(seed).hexdigest()[:16]}"

    def used(self, profile: str, reference: str) -> None:
        if (profile, reference) not in self._used:
            self._used.append((profile, reference))

    def __enter__(self) -> CredentialDataset:
        staging = Path(tempfile.mkdtemp(prefix="pharma-cred-"))
        staging.chmod(0o700)
        for file in self.files:
            destination = staging / file.name
            shutil.copyfile(self._source / file.name, destination)
            destination.chmod(0o600)
        if self._template is not None:
            # Without the local api-keys and management secret: the kernel ignores them.
            (staging / CONFIG_NAME).write_text(
                "\n".join(
                    without_forced_keys(self._template.read_text(encoding="utf-8"))
                )
                + "\n",
                encoding="utf-8",
            )
            (staging / CONFIG_NAME).chmod(0o600)
        self._staging = staging
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        for profile, reference in self._used:
            self._delete(profile, reference)
        if self._staging is not None:
            shutil.rmtree(self._staging, ignore_errors=True)
            self._staging = None

    def _delete(self, profile: str, reference: str) -> None:
        for attempt in range(1, DELETE_ATTEMPTS + 1):
            try:
                self._deleter(profile, reference)
                return
            except Exception as error:  # whatever it is, the dataset must be reported
                self._say(
                    f"could not delete {reference} (attempt {attempt}/"
                    f"{DELETE_ATTEMPTS}, will retry): {type(error).__name__}"
                )
                time.sleep(self._retry_pause)
        self._say(
            f"!! CREDENTIALS ARE STILL ON KAGGLE: {reference} ({profile}). Delete it: "
            f"kaggle datasets delete {reference}"
        )
