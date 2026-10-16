import csv
import json
from pathlib import Path

import pytest

from pharma_lab.e2e.calibration import calibration_dir
from pharma_lab.e2e.configs import E2EConfig
from pharma_lab.e2e.golden import GoldenItem
from pharma_lab.e2e.records import (
    AnswerRecord,
    CitedSection,
    JsonlStore,
    Judgement,
    RetrievedChunk,
    RoundRecord,
    TokenUsage,
)
from pharma_lab.e2e.report import (
    CONFIG_LABELS,
    METRIC_LABELS,
    METRICS,
    ItemView,
    _number,
    bootstrap_mean,
    error_label,
    paired_delta,
    write_report,
)
from pharma_lab.evaluation.relevance_judgments import LoadedJudgments

SECTION = "drug:x:lieu-dung"


def golden(n: int) -> GoldenItem:
    return GoldenItem.model_validate(
        {
            "item_id": f"e2e-ans-{n:04d}",
            "category": "answerable",
            "turns": [{"role": "user", "text": f"Câu {n} | liều?"}],
            "expected_behavior": "grounded",
            "gold_section_ids": [SECTION],
            "reference": {
                "answer": "r",
                "key_facts": [
                    {"fact": "f", "evidence_quote": "q", "section_id": SECTION}
                ],
            },
            "eval_group": "formulary" if n % 2 else "leaflet",
        }
    )


def answer(n: int, config: str, *, retrieved: str = SECTION) -> AnswerRecord:
    return AnswerRecord(
        item_id=f"e2e-ans-{n:04d}",
        config=config,
        status="completed",
        answer_mode="grounded",
        citations=[
            CitedSection(
                index=1, chunk_version_id="c", chunk_id=None, section_ids=[SECTION]
            )
        ],
        retrieved=[
            RetrievedChunk(chunk_id="drug:x:chunk-001", section_ids=[retrieved])
        ],
        llm_calls=4 if config == "full" else 2,
        usage_by_role={
            "answer": TokenUsage(calls=1, prompt_tokens=100, completion_tokens=10)
        },
        latency_seconds=float(n),
    )


def judgement(n: int, config: str, recall: float) -> Judgement:
    return Judgement(
        item_id=f"e2e-ans-{n:04d}",
        config=config,
        category="answerable",
        behaviour_correct=True,
        key_fact_recall=recall,
        contradiction=False,
        faithfulness=recall,
        citation_precision=1.0,
        citation_recall=1.0,
    )


IDENTITY = {
    "role_models": {
        role: {"model": "gemini-3.8-flash-high"}
        for role in ("guardrail", "rephrase", "judge", "refine", "answer", "summarizer")
    },
    "retrieval": {"embedding_model": "qwen3-embedding:4b-q8_0"},
    "rerank": {"model": "qwen3-reranker:4b-q8_0"},
}


def write_identity(root: Path, config: str) -> None:
    (root / config).mkdir(parents=True, exist_ok=True)
    (root / config / "run.json").write_text(json.dumps(IDENTITY), encoding="utf-8")


def write_config(root: Path, config: str, recalls: list[float]) -> None:
    write_identity(root, config)
    answers = JsonlStore(root / config / "answers.jsonl", AnswerRecord)
    judgments = JsonlStore(root / config / "judgments.jsonl", Judgement)
    for n, recall in enumerate(recalls):
        answers.append(answer(n, config, retrieved="other" if n == 0 else SECTION))
        judgments.append(judgement(n, config, recall))


def rows(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.read_text("utf-8").splitlines()))


def test_bootstrap_mean_and_paired_delta() -> None:
    summary = bootstrap_mean([1.0, 1.0, 1.0])
    assert (summary.n, summary.mean, summary.ci_low, summary.ci_high) == (
        3,
        1.0,
        1.0,
        1.0,
    )
    empty = bootstrap_mean([])
    assert empty.n == 0
    delta = paired_delta({"a": 1.0, "b": 0.5, "c": 0.0}, {"a": 0.5, "b": 0.0})
    assert delta.n == 2
    assert delta.mean == pytest.approx(-0.5)


def test_error_labels() -> None:
    item = golden(1)
    assert error_label(item, answer(1, "full", retrieved="other")) == "retrieval"
    uncited = answer(1, "full").model_copy(update={"citations": []})
    assert error_label(item, uncited) == "citation"
    assert error_label(item, answer(1, "full")) == "answer"


def test_write_report_builds_every_table(tmp_path: Path) -> None:
    items = {golden(n).item_id: golden(n) for n in range(6)}
    write_config(tmp_path, "full", [1.0, 1.0, 0.5, 1.0, 0.0, 1.0])
    write_config(tmp_path, "one-step", [0.5, 0.5, 0.5, 0.5, 0.0, 0.5])
    directory = calibration_dir(tmp_path)
    directory.mkdir()
    (directory / "agreement.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "metric": "key_fact_supported",
                        "statistic": "cohen_kappa",
                        "n": 20,
                        "value": 0.8,
                        "ci_low": 0.6,
                        "ci_high": 0.9,
                        "reliable": True,
                    },
                    {
                        "metric": "injection_followed",
                        "statistic": "cohen_kappa",
                        "n": 0,
                        "value": None,
                        "ci_low": None,
                        "ci_high": None,
                        "reliable": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    written = write_report(tmp_path, items)

    assert sorted(path.name for path in written) == [
        "ablation.csv",
        "ablation.tex",
        "by_group.csv",
        "calibration.csv",
        "calibration.tex",
        "cost.csv",
        "cost.tex",
        "errors.md",
        "main.csv",
        "main.tex",
        "provenance.json",
    ]
    reports = tmp_path / "reports"
    main = rows(reports / "main.csv")
    recall = {r["config"]: r for r in main if r["metric"] == "nugget_recall"}
    assert float(recall["full"]["mean"]) == pytest.approx(0.75)
    assert float(recall["one-step"]["mean"]) == pytest.approx(5 / 12)
    calls = {
        r["config"]: float(r["mean"])
        for r in main
        if r["metric"] == "llm_calls_per_turn"
    }
    assert calls == {"full": 4.0, "one-step": 2.0}
    ablation = rows(reports / "ablation.csv")
    delta = next(r for r in ablation if r["metric"] == "nugget_recall")
    assert delta["config"] == "one-step"
    assert float(delta["delta"]) == pytest.approx(5 / 12 - 0.75)
    assert 0 < float(delta["p_value"]) <= 1
    assert float(delta["p_holm"]) == pytest.approx(float(delta["p_value"]))
    groups = rows(reports / "by_group.csv")
    assert {r["group"] for r in groups} == {"answerable", "formulary", "leaflet"}
    tex = (reports / "main.tex").read_text("utf-8")
    assert r"\label{tab:e2e-main}" in tex
    assert r"\toprule" in tex and r"\hline" not in tex
    assert r"Nugget recall $\uparrow$" in tex and r"Truthfulness $\uparrow$" in tex
    assert "Full agent & One-step RAG" in tex
    assert "latency" not in tex.lower()  # latency is secondary: CSV only
    assert "0.750 [" in tex
    calls_row = next(line for line in tex.splitlines() if line.startswith("LLM calls"))
    assert calls_row.startswith(r"LLM calls / turn $\downarrow$ & 4.0 [")
    ablation_tex = (reports / "ablation.tex").read_text("utf-8")
    assert r"\label{tab:e2e-ablation}" in ablation_tex
    assert "One-step RAG" in ablation_tex
    nugget_row = next(
        line for line in ablation_tex.splitlines() if line.startswith("Nugget recall")
    )
    assert nugget_row.startswith(r"Nugget recall $\uparrow$ & $-$0.333")
    assert "[" not in nugget_row  # CIs stay in ablation.csv
    calibration_tex = (reports / "calibration.tex").read_text("utf-8")
    assert r"\label{tab:e2e-calibration}" in calibration_tex
    assert "--" in calibration_tex
    errors = (reports / "errors.md").read_text("utf-8").splitlines()
    assert errors[4].startswith("| e2e-ans-0004 | answerable | 0.00 | -- |")
    assert "| retrieval |" in next(line for line in errors if "e2e-ans-0000" in line)
    assert "Câu 4 / liều?" in errors[4]


def test_report_needs_judged_answers(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no judged configuration"):
        write_report(tmp_path, {})


def test_report_uses_relevance_judgments_and_answerable_groups(tmp_path: Path) -> None:
    item = golden(1).model_copy(update={"source_query_id": "q-1"})
    leaflet = "leaflet:x:chunk-001"
    answers = JsonlStore(tmp_path / "full" / "answers.jsonl", AnswerRecord)
    answers.append(
        answer(1, "full").model_copy(
            update={
                "citations": [
                    CitedSection(
                        index=1,
                        chunk_version_id="c",
                        chunk_id=leaflet,
                        section_ids=["leaflet:x"],
                    )
                ]
            }
        )
    )
    JsonlStore(tmp_path / "full" / "judgments.jsonl", Judgement).append(
        judgement(1, "full", 1.0)
    )
    relevance = LoadedJudgments("r" * 64, {"q-1": {SECTION: frozenset({leaflet})}})
    write_identity(tmp_path, "full")

    write_report(tmp_path, {item.item_id: item}, relevance)
    main = {r["metric"]: r for r in rows(tmp_path / "reports" / "main.csv")}
    assert float(main["cited_source_precision"]["mean"]) == 1.0
    assert main["over_refusal_rate"]["n"] == "1"
    provenance = json.loads((tmp_path / "reports" / "provenance.json").read_text())
    assert provenance["relevance_judgments_sha256"] == "r" * 64

    write_report(tmp_path, {item.item_id: item})
    main = {r["metric"]: r for r in rows(tmp_path / "reports" / "main.csv")}
    assert float(main["cited_source_precision"]["mean"]) == 0.0


def test_every_primary_metric_and_config_has_a_paper_label() -> None:
    assert {m.name for m in METRICS if m.primary} <= set(METRIC_LABELS)
    assert {c.value for c in E2EConfig} == set(CONFIG_LABELS)


def test_numbers_keep_three_decimals_up_to_one() -> None:
    assert _number(1.0) == "1.000"
    assert _number(-1.0) == "$-$1.000"
    assert _number(0.5) == "0.500"
    assert _number(5.2) == "5.2"
    assert _number(11278.4) == "11278"


def _loop_view(rounds: list[list[str]], gold: list[str]) -> ItemView:
    item = golden(1).model_copy(update={"gold_section_ids": gold})
    record = answer(1, "full").model_copy(
        update={
            "rounds": [
                RoundRecord(sections=s, chunks=len(s), evidence_chars=1000 * len(s))
                for s in rounds
            ]
        }
    )
    return ItemView(item, record, judgement(1, "full", 1.0), {})


def _metric(name: str):
    return next(metric for metric in METRICS if metric.name == name).read


def test_loop_metrics_measure_gold_found_per_search_round() -> None:
    gold = ["drug:x:lieu-dung", "drug:x:chi-dinh"]
    rescued = _loop_view([["drug:x:lieu-dung"], list(gold)], gold)
    assert _metric("gold_coverage_round1")(rescued) == 0.5
    assert _metric("gold_coverage_final")(rescued) == 1.0
    assert _metric("rounds_used")(rescued) == 2.0
    assert _metric("rescued_rate")(rescued) == 1.0
    assert _metric("evidence_chars_final")(rescued) == 2000.0
    first_round_enough = _loop_view([list(gold)], gold)
    assert _metric("rescued_rate")(first_round_enough) is None
    closed_book = _loop_view([], gold)
    assert _metric("gold_coverage_round1")(closed_book) is None
    assert _metric("rounds_used")(closed_book) is None


def test_seconds_per_turn_metrics_read_steps_and_roles() -> None:
    record = answer(1, "full").model_copy(
        update={
            "retrieval_seconds": 0.4,
            "rerank_seconds": 0.6,
            "usage_by_role": {
                "guardrail": TokenUsage(calls=1, seconds=0.2),
                "judge": TokenUsage(calls=1, seconds=0.3),
                "answer": TokenUsage(calls=1, seconds=2.0),
            },
        }
    )
    view = ItemView(golden(1), record, judgement(1, "full", 1.0), {})
    by_name = {metric.name: metric for metric in METRICS}
    assert by_name["llm_seconds_per_turn"].read(view) == pytest.approx(2.5)
    assert by_name["retrieval_seconds_per_turn"].read(view) == pytest.approx(1.0)
    assert by_name["rerank_seconds_per_turn"].read(view) == pytest.approx(0.6)
    assert by_name["decision_seconds_per_turn"].read(view) == pytest.approx(0.5)


def test_cost_table_has_usd_per_turn_and_cost_of_pass(tmp_path: Path) -> None:
    items = {golden(n).item_id: golden(n) for n in range(4)}
    write_config(tmp_path, "full", [1.0, 1.0, 0.5, 1.0])

    write_report(tmp_path, items)

    table = {r["metric"]: r for r in rows(tmp_path / "reports" / "cost.csv")}
    assert {"usd_per_turn", "usd_per_1000_turns", "cost_of_pass", "latency_p50"} <= set(
        table
    )
    # answer: 100 prompt + 10 completion tokens on gemini-3.8-flash-high per turn.
    llm = (100 * 0.75 + 10 * 3.75) / 1e6
    assert float(table["llm_usd_per_turn"]["mean"]) == pytest.approx(llm)
    assert float(table["usd_per_1000_turns"]["mean"]) == pytest.approx(
        1000 * float(table["usd_per_turn"]["mean"])
    )
    tex = (tmp_path / "reports" / "cost.tex").read_text("utf-8")
    assert r"\label{tab:e2e-cost}" in tex
