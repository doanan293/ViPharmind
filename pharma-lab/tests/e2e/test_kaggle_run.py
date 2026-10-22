import io
import json
import tarfile
from pathlib import Path

import pytest
from tests.e2e.test_report import golden

from pharma_lab.e2e.golden import Category
from pharma_lab.e2e.kaggle_run import (
    check_targets,
    extract_outputs,
    job_items,
    trimmed_corpus,
)


def test_job_items_are_the_golden_items_of_the_categories() -> None:
    items = [golden(n) for n in range(3)]

    assert job_items(items, [Category.ANSWERABLE]) == [i.item_id for i in items]
    with pytest.raises(ValueError, match="no golden item"):
        job_items(items, [Category.INJECTION])


def test_trimmed_corpus_keeps_one_embedding_model(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    (bundle / "embeddings").mkdir(parents=True)
    for name in ("documents.jsonl", "embeddings/a.jsonl", "embeddings/b.jsonl"):
        (bundle / name).write_text(name, encoding="utf-8")
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "collection": {"key": "formulary"},
                "files": {
                    "documents.jsonl": {"sha256": "d"},
                    "embeddings/a.jsonl": {"sha256": "a"},
                    "embeddings/b.jsonl": {"sha256": "b"},
                },
                "embeddings": [
                    {"model": "m-a", "dims": 2, "file": "embeddings/a.jsonl"},
                    {"model": "m-b", "dims": 2, "file": "embeddings/b.jsonl"},
                ],
            }
        ),
        encoding="utf-8",
    )

    target = trimmed_corpus(bundle, tmp_path / "corpus", embedding_model="m-b")
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))

    assert sorted(manifest["files"]) == ["documents.jsonl", "embeddings/b.jsonl"]
    assert [e["model"] for e in manifest["embeddings"]] == ["m-b"]
    assert (target / "embeddings/b.jsonl").read_text(encoding="utf-8") == (
        "embeddings/b.jsonl"
    )
    assert not (target / "embeddings/a.jsonl").exists()


def test_targets_with_answers_are_refused(tmp_path: Path) -> None:
    (tmp_path / "no-rerank").mkdir()
    (tmp_path / "no-rerank/answers.jsonl").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="already has answers"):
        check_targets(tmp_path, ["no-rerank"])
    check_targets(tmp_path, ["no-guard-no-rerank"])


def tar_with(tmp_path: Path, names: list[str]) -> Path:
    path = tmp_path / "out.tar"
    with tarfile.open(path, "w") as archive:
        for name in names:
            data = b"{}\n"
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return path


def test_outputs_are_extracted_into_the_run(tmp_path: Path) -> None:
    archive = tar_with(tmp_path, ["no-rerank/answers.jsonl", "no-rerank/run.json"])

    written = extract_outputs(archive, tmp_path / "run", ["no-rerank"])

    assert sorted(p.relative_to(tmp_path / "run").as_posix() for p in written) == [
        "no-rerank/answers.jsonl",
        "no-rerank/run.json",
    ]


@pytest.mark.parametrize(
    "name", ["../evil.jsonl", "other/answers.jsonl", "no-rerank/x.log"]
)
def test_unexpected_members_are_refused(tmp_path: Path, name: str) -> None:
    archive = tar_with(tmp_path, ["no-rerank/answers.jsonl", name])

    with pytest.raises(ValueError, match="unexpected"):
        extract_outputs(archive, tmp_path / "run", ["no-rerank"])
    assert not (tmp_path / "run").exists()
