import json
from pathlib import Path

import pytest

from pharma_lab.e2e import kaggle_run
from pharma_lab.e2e.kaggle_run import trimmed_corpus


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


def test_static_inputs_hold_the_golden_set_requirements_and_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "documents.jsonl").write_text("d", encoding="utf-8")
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "files": {"documents.jsonl": {"sha256": "d"}},
                "embeddings": [],
            }
        ),
        encoding="utf-8",
    )
    golden_path = tmp_path / "golden.jsonl"
    golden_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(kaggle_run, "BUNDLE_DIR", bundle)
    monkeypatch.setattr(
        kaggle_run, "_requirements", lambda target: target.write_text("x==1\n")
    )

    kaggle_run.build_static_inputs(golden_path, tmp_path / "static")

    assert sorted(p.name for p in (tmp_path / "static").iterdir()) == [
        "backend_requirements.txt",
        "corpus",
        "golden_e2e.jsonl",
    ]
    assert (tmp_path / "static/corpus/documents.jsonl").is_file()
