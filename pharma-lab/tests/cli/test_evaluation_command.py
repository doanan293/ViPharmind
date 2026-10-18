import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

import pharma_lab.cli.commands.evaluation as evaluation_command
from pharma_lab.cli.app import app

runner = CliRunner()


def test_evaluation_build_derives_chunks_from_the_bundle(tmp_path, monkeypatch):
    from pharma_lab.bundle.export import ExportRequest, export_bundle
    from pharma_lab.evaluation.build_dataset import EvaluationBuildResult

    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "rag_final_small"
    export_bundle(
        ExportRequest(
            rag_final_dir=fixture,
            glossary_path=fixture / "term_glossary.json",
            mappings_path=fixture / "colloquial_mappings.json",
            output_dir=tmp_path / "bundle",
        )
    )
    captured = {}

    def fake_build(request):
        captured["request"] = request
        return EvaluationBuildResult(
            tmp_path / "patient_queries.json", tmp_path / "evaluation.jsonl", 0, 0
        )

    def fake_judgments(evaluation_path, bundle_dir):
        captured["judgments"] = (evaluation_path, bundle_dir)
        return tmp_path / "evaluation.judgments.jsonl"

    monkeypatch.setattr(evaluation_command, "build_evaluation_dataset", fake_build)
    monkeypatch.setattr(
        evaluation_command, "build_evaluation_judgments", fake_judgments
    )
    result = runner.invoke(
        app,
        [
            "--json",
            "evaluation",
            "build",
            "--sections",
            str(fixture / "sections.jsonl"),
            "--bundle",
            str(tmp_path / "bundle"),
            "--chunks-output",
            str(tmp_path / "chunks.jsonl"),
            "--output-dir",
            str(tmp_path / "evaluation"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["request"].chunks_path == tmp_path / "chunks.jsonl"
    from pharma_agent.domain.corpus.bundle import read_bundle

    from pharma_lab.bundle.evaluation_chunks import evaluation_chunk_rows

    expected = len(evaluation_chunk_rows(read_bundle(tmp_path / "bundle")))
    assert expected >= 2
    assert len((tmp_path / "chunks.jsonl").read_text("utf-8").splitlines()) == expected
    details = json.loads(result.stdout)["details"]
    assert details["chunks"] == expected
    assert captured["judgments"] == (tmp_path / "evaluation.jsonl", tmp_path / "bundle")
    assert details["judgments"] == str(tmp_path / "evaluation.judgments.jsonl")


def test_evaluation_judgments_rebuild_only_the_judgments(tmp_path, monkeypatch):
    captured = {}

    def fake_judgments(evaluation_path, bundle_dir):
        captured["args"] = (evaluation_path, bundle_dir)
        return tmp_path / "gold.judgments.jsonl"

    monkeypatch.setattr(
        evaluation_command, "build_evaluation_judgments", fake_judgments
    )

    result = runner.invoke(
        app,
        [
            "--json",
            "evaluation",
            "judgments",
            "--evaluation",
            str(tmp_path / "gold.jsonl"),
            "--bundle",
            str(tmp_path / "bundle"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["args"] == (tmp_path / "gold.jsonl", tmp_path / "bundle")
    assert json.loads(result.stdout)["artifact"] == str(
        tmp_path / "gold.judgments.jsonl"
    )


def test_evaluation_extend_rewrites_the_gold_file_and_its_judgments(
    tmp_path, monkeypatch
):
    from pharma_lab.e2e.corpus_text import CorpusText

    gold = tmp_path / "gold.jsonl"
    base = [{"query_id": "q1", "query": "Liều?", "eval_group": "formulary"}]
    gold.write_text(json.dumps(base[0]) + "\n", encoding="utf-8")
    calls: dict[str, object] = {}
    mapping = SimpleNamespace(
        aliases=["Panadol đỏ"], section_keys=["leaflet:t:p:01-thanh-phan"]
    )
    knowledge = SimpleNamespace(colloquial_mappings=[mapping])

    def fake_extend(rows, corpus, aliases, *, covered, conversational_total, seed):
        calls["extend"] = (rows, aliases, covered, conversational_total, seed)
        return [*rows, {"query_id": "conv-0001", "eval_group": "conversational"}]

    def fake_judgments(evaluation_path, bundle_dir):
        calls["judgments"] = (evaluation_path, bundle_dir)
        return tmp_path / "gold.judgments.jsonl"

    monkeypatch.setattr(evaluation_command, "read_bundle", lambda path: knowledge)
    monkeypatch.setattr(
        evaluation_command,
        "corpus_text",
        lambda knowledge: CorpusText(sections={}, section_documents={}, titles={}),
    )
    monkeypatch.setattr(evaluation_command, "extend_rows", fake_extend)
    monkeypatch.setattr(
        evaluation_command, "build_evaluation_judgments", fake_judgments
    )

    result = runner.invoke(
        app,
        [
            "--json",
            "evaluation",
            "extend",
            "--evaluation",
            str(gold),
            "--bundle",
            str(tmp_path / "bundle"),
            "--run",
            "",
            "--conversational-total",
            "16",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls["extend"] == (
        base,
        [("Panadol đỏ", ["leaflet:t:p:01-thanh-phan"])],
        None,
        16,
        0,
    )
    written = [json.loads(line) for line in gold.read_text("utf-8").splitlines()]
    assert [row["query_id"] for row in written] == ["q1", "conv-0001"]
    assert calls["judgments"] == (gold, tmp_path / "bundle")
    details = json.loads(result.stdout)["details"]
    assert (details["rows"], details["formulary"], details["conversational"]) == (
        2,
        1,
        1,
    )
