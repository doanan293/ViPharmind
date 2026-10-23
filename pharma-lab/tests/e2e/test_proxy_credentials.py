from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable
from pathlib import Path

import pytest

from pharma_lab.config.paths import DATA_DIR
from pharma_lab.e2e.proxy_credentials import (
    CredentialDataset,
    export_credentials_from_volume,
    list_credentials,
    select_credentials,
)

SECRET = "ya29.THIS-MUST-NEVER-BE-PRINTED"


def write_credential(directory: Path, name: str, kind: str) -> None:
    (directory / name).write_text(
        json.dumps({"type": kind, "access_token": SECRET, "email": "a@b.c"}),
        encoding="utf-8",
    )


@pytest.fixture
def source(tmp_path: Path) -> Path:
    directory = tmp_path / "auth"
    directory.mkdir()
    write_credential(directory, "antigravity-a.json", "antigravity")
    write_credential(directory, "claude-b.json", "claude")
    write_credential(directory, "codex-c.json", "codex")
    (directory / "notes.txt").write_text("ignored", encoding="utf-8")
    (directory / "broken.json").write_text("{not json", encoding="utf-8")
    return directory


def test_list_credentials_reads_only_the_type_field(source: Path, capsys) -> None:
    files = list_credentials(source)

    assert [(f.name, f.type) for f in files] == [
        ("antigravity-a.json", "antigravity"),
        ("broken.json", "invalid"),
        ("claude-b.json", "claude"),
        ("codex-c.json", "codex"),
    ]
    shown = capsys.readouterr().out + repr(files)
    assert SECRET not in shown
    assert "a@b.c" not in shown


def test_selection_follows_the_providers_of_the_preset(source: Path) -> None:
    files = list_credentials(source)

    gemini = select_credentials(files, frozenset({"antigravity"}), ())
    assert [f.name for f in gemini] == ["antigravity-a.json"]
    named = select_credentials(files, frozenset({"claude"}), ("codex-c.json",))
    assert [f.name for f in named] == ["codex-c.json"]
    with pytest.raises(ValueError, match="no credential file"):
        select_credentials(files, frozenset({"gemini-cli"}), ())
    with pytest.raises(ValueError, match=r"missing\.json"):
        select_credentials(files, frozenset({"claude"}), ("missing.json",))


def test_the_export_copies_json_files_out_of_the_volume(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def docker(command: list[str], **_kwargs: object) -> None:
        calls.append(command)

    export_credentials_from_volume("vol", tmp_path / "out", run=docker)

    command = calls[0]
    assert command[:3] == ["docker", "run", "--rm"]
    assert "vol:/auth:ro" in command
    # The container runs as root: the files must end up owned by the caller.
    script = command[-1]
    assert f"chown {os.getuid()}:{os.getgid()}" in script
    assert (tmp_path / "out").is_dir()
    assert stat.S_IMODE(os.stat(tmp_path / "out").st_mode) == 0o700


class Deleter:
    def __init__(self, fail_times: int = 0) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_times = fail_times

    def __call__(self, profile: str, reference: str) -> None:
        self.calls.append((profile, reference))
        if len(self.calls) <= self.fail_times:
            raise RuntimeError("kaggle said no")


def dataset(
    source: Path, deleter: Callable[[str, str], None], **kwargs
) -> CredentialDataset:
    files = select_credentials(list_credentials(source), frozenset({"claude"}), ())
    return CredentialDataset(
        source,
        files,
        run_name="r1",
        template=None,
        deleter=deleter,
        say=kwargs.pop("say", lambda _line: None),
        **kwargs,
    )


def test_staging_holds_only_the_selected_files_outside_the_repository(
    source: Path,
) -> None:
    with dataset(source, Deleter()) as credentials:
        staged = credentials.stage_dir
        assert sorted(p.name for p in staged.iterdir()) == ["claude-b.json"]
        assert DATA_DIR not in staged.parents
        assert stat.S_IMODE(os.stat(staged).st_mode) == 0o700
    assert not staged.exists()


def test_slug_is_stable_per_run_and_account_and_never_leaks_content(
    source: Path,
) -> None:
    with dataset(source, Deleter()) as credentials:
        one = credentials.slug("acc1")
        assert one == credentials.slug("acc1")
        assert one != credentials.slug("acc2")
        assert one.startswith("pipeline-cred-")
        assert SECRET not in one


def test_credential_dataset_is_deleted_on_exit_and_on_error(source: Path) -> None:
    deleter = Deleter()
    with dataset(source, deleter) as credentials:
        credentials.used("acc1", "user1/pipeline-cred-x")
        credentials.used("acc2", "user2/pipeline-cred-y")
    assert deleter.calls == [
        ("acc1", "user1/pipeline-cred-x"),
        ("acc2", "user2/pipeline-cred-y"),
    ]

    failing = Deleter()
    with pytest.raises(KeyError), dataset(source, failing) as credentials:
        credentials.used("acc1", "user1/pipeline-cred-x")
        raise KeyError("boom")
    assert failing.calls == [("acc1", "user1/pipeline-cred-x")]


def test_failed_deletion_is_retried_and_reported(source: Path) -> None:
    deleter = Deleter(fail_times=2)
    said: list[str] = []

    with dataset(source, deleter, say=said.append, retry_pause=0.0) as credentials:
        credentials.used("acc1", "user1/pipeline-cred-x")

    assert len(deleter.calls) == 3
    assert any("pipeline-cred-x" in line and "retry" in line for line in said)


def test_a_deletion_that_keeps_failing_is_reported_loudly(source: Path) -> None:
    deleter = Deleter(fail_times=99)
    said: list[str] = []

    with dataset(source, deleter, say=said.append, retry_pause=0.0) as credentials:
        credentials.used("acc1", "user1/pipeline-cred-x")

    assert len(deleter.calls) == 3
    loud = [line for line in said if "STILL ON KAGGLE" in line]
    assert loud
    assert "kaggle datasets delete user1/pipeline-cred-x" in loud[0]
    assert SECRET not in " ".join(said)


def test_the_staged_proxy_config_drops_the_local_keys_and_management_secret(
    source: Path, tmp_path: Path
) -> None:
    template = tmp_path / "config.yaml"
    template.write_text(
        'host: ""\napi-keys:\n  - "local-secret-key"\nremote-management:\n'
        '  secret-key: "management-hash"\npayload:\n  keep: true\n',
        encoding="utf-8",
    )
    files = select_credentials(list_credentials(source), frozenset({"claude"}), ())
    credentials = CredentialDataset(
        source,
        files,
        run_name="r1",
        template=template,
        deleter=Deleter(),
        say=lambda _line: None,
    )

    with credentials:
        staged = (credentials.stage_dir / "proxy-config.yaml").read_text()

    assert "payload:" in staged and "keep: true" in staged
    assert "local-secret-key" not in staged
    assert "management-hash" not in staged


def test_a_deleter_that_raises_something_unexpected_does_not_hide_the_leftovers(
    source: Path,
) -> None:
    said: list[str] = []

    def broken(profile: str, reference: str) -> None:
        raise ValueError("no such account")

    with dataset(source, broken, say=said.append, retry_pause=0.0) as credentials:
        credentials.used("acc1", "user1/pipeline-cred-x")
        credentials.used("acc2", "user2/pipeline-cred-y")

    loud = [line for line in said if "STILL ON KAGGLE" in line]
    assert len(loud) == 2
