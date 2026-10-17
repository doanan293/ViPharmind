import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pharma_lab.cli.app import app

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "rag_final_small"
runner = CliRunner()


def test_bundle_export_command_writes_a_valid_bundle(tmp_path: Path) -> None:
    output = tmp_path / "bundle"

    result = runner.invoke(
        app,
        [
            "--json",
            "bundle",
            "export",
            "--output",
            str(output),
            "--rag-final-dir",
            str(FIXTURE),
            "--glossary",
            str(FIXTURE / "term_glossary.json"),
            "--mappings",
            str(FIXTURE / "colloquial_mappings.json"),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "complete"
    assert payload["details"] == {"documents": 4, "sections": 5, "skipped_sections": []}
    assert (output / "manifest.json").is_file()


def _export(output: Path) -> None:
    result = runner.invoke(
        app,
        [
            "bundle",
            "export",
            "--output",
            str(output),
            "--rag-final-dir",
            str(FIXTURE),
            "--glossary",
            str(FIXTURE / "term_glossary.json"),
            "--mappings",
            str(FIXTURE / "colloquial_mappings.json"),
        ],
    )
    assert result.exit_code == 0, result.output


def test_bundle_embed_command_uses_the_selected_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.bundle.test_embed import CacheFillingBackend

    import pharma_lab.cli.commands.bundle as bundle_command

    _export(tmp_path / "bundle")
    created: list[CacheFillingBackend] = []

    def kaggle_backend() -> CacheFillingBackend:
        backend = CacheFillingBackend()
        created.append(backend)
        return backend

    monkeypatch.setattr(bundle_command, "KaggleTextEmbeddingBackend", kaggle_backend)

    result = runner.invoke(
        app,
        [
            "--json",
            "bundle",
            "embed",
            "--bundle",
            str(tmp_path / "bundle"),
            "--backend",
            "kaggle",
            "--model",
            "qwen3-embedding:4b-q8_0",
            "--cache",
            str(tmp_path / "cache.jsonl"),
            "--work-dir",
            str(tmp_path / "work"),
            "--kaggle-account",
            "acc2",
        ],
    )

    assert result.exit_code == 0, result.output
    from pharma_agent.domain.corpus.bundle import read_bundle

    from pharma_lab.bundle.embed import collect_embedding_inputs

    expected = len(collect_embedding_inputs(read_bundle(tmp_path / "bundle")))
    details = json.loads(result.output)["details"]
    assert expected >= 2
    assert (details["inputs"], details["vectors"]) == (expected, expected)
    assert created[0].requests[0].kaggle_account == "acc2"


def test_bundle_rechunk_command_writes_a_bundle_with_the_new_chunking(
    tmp_path: Path,
) -> None:
    _export(tmp_path / "bundle")
    output = tmp_path / "sections"

    result = runner.invoke(
        app,
        [
            "--json",
            "bundle",
            "rechunk",
            "--bundle",
            str(tmp_path / "bundle"),
            "--out",
            str(output),
            "--collection",
            "formulary_sections",
            "--title",
            "Một chunk mỗi mục",
            "--target-chars",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "complete"
    assert payload["details"] == {
        "collection": "formulary_sections",
        "target_chars": 1,
        "max_chars": 5600,
        "enrichment": True,
        "documents": 4,
        "sections": 5,
    }
    manifest = json.loads((output / "manifest.json").read_text("utf-8"))
    assert manifest["chunking"] == {"target_chars": 1, "max_chars": 5600}
