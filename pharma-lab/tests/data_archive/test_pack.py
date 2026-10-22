import hashlib
from pathlib import Path

import pytest
from tests.data_archive.archive_project import FILES, make_project

from pharma_lab.data_archive.manifest import (
    PART_PREFIX,
    ArchiveError,
    ArchiveFile,
    ArchiveManifest,
    ArchivePart,
    read_archive_manifest,
    write_archive_manifest,
)
from pharma_lab.data_archive.pack import git_head, list_archive_files, pack_archive


def test_only_ignored_files_outside_work_are_archived(tmp_path: Path) -> None:
    root = make_project(tmp_path / "project")

    assert list_archive_files(root) == sorted(FILES)


def test_symbolic_links_in_data_are_refused(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    (root / "data" / "cache" / "linked").symlink_to(root / "data" / "cache")

    with pytest.raises(ArchiveError, match="cache/linked"):
        list_archive_files(root)


def test_pack_splits_the_stream_into_numbered_parts(tmp_path: Path) -> None:
    root = make_project(tmp_path / "project")

    manifest = pack_archive(
        root / "data",
        list_archive_files(root),
        tmp_path / "archive",
        part_size=1024,
        created_at="2026-09-14T00:00:00+00:00",
        git_commit=git_head(root),
    )

    assert len(manifest.parts) > 1
    assert [part.name for part in manifest.parts] == [
        f"{PART_PREFIX}{index:04d}" for index in range(1, len(manifest.parts) + 1)
    ]
    for part in manifest.parts:
        path = tmp_path / "archive" / part.name
        assert part.size == path.stat().st_size <= 1024
        assert part.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert manifest.files == tuple(
        ArchiveFile(relative, len(payload), hashlib.sha256(payload).hexdigest())
        for relative, payload in sorted(FILES.items())
    )
    assert len(manifest.git_commit) == 40


def test_manifest_round_trips(tmp_path: Path) -> None:
    manifest = ArchiveManifest(
        "2026-09-14T00:00:00+00:00",
        "c" * 40,
        (ArchiveFile("cache/a.jsonl", 3, "a" * 64),),
        (ArchivePart(f"{PART_PREFIX}0001", 10, "b" * 64),),
    )
    path = tmp_path / "archive-manifest.json"

    write_archive_manifest(path, manifest)

    assert read_archive_manifest(path) == manifest


@pytest.mark.parametrize(
    "unsafe", ["../escape.txt", "/etc/passwd", "work/locks/probe.job.lock", "./x"]
)
def test_manifest_rejects_unsafe_paths(tmp_path: Path, unsafe: str) -> None:
    path = tmp_path / "archive-manifest.json"
    write_archive_manifest(
        path,
        ArchiveManifest(
            "2026-09-14T00:00:00+00:00",
            "c" * 40,
            (ArchiveFile(unsafe, 1, "a" * 64),),
            (),
        ),
    )

    with pytest.raises(ArchiveError, match="Unsafe archive path"):
        read_archive_manifest(path)


def test_manifest_accepts_the_part_names_of_a_renamed_dataset(tmp_path: Path) -> None:
    manifest = ArchiveManifest(
        "2026-10-14T00:00:00+00:00",
        "c" * 40,
        (ArchiveFile("cache/a.jsonl", 3, "a" * 64),),
        (ArchivePart("vipharmind-data.tar.zst.part-0001", 10, "b" * 64),),
    )
    path = tmp_path / "archive-manifest.json"
    write_archive_manifest(path, manifest)

    assert read_archive_manifest(path) == manifest


@pytest.mark.parametrize(
    "name", ["../seed.tar.zst.part-0001", "data.tar.zst.part-1", "data.zip"]
)
def test_manifest_rejects_other_part_names(tmp_path: Path, name: str) -> None:
    path = tmp_path / "archive-manifest.json"
    write_archive_manifest(
        path,
        ArchiveManifest(
            "2026-10-14T00:00:00+00:00",
            "c" * 40,
            (),
            (ArchivePart(name, 10, "b" * 64),),
        ),
    )

    with pytest.raises(ArchiveError, match="Unexpected archive part name"):
        read_archive_manifest(path)
