"""Runs on disk for the report and compare tests."""

import csv
import json
from pathlib import Path

from pharma_lab.e2e.golden import GoldenItem
from pharma_lab.e2e.records import (
    AnswerRecord,
    CitedSection,
    JsonlStore,
    Judgement,
    RetrievedChunk,
    TokenUsage,
)

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
