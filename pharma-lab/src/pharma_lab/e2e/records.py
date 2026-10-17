"""Per-item records of an E2E run, stored as append-only JSONL (spec §6.2)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_RECORD = ConfigDict(extra="forbid")
ANSWERS_FILE = "answers.jsonl"
JUDGMENTS_FILE = "judgments.jsonl"


class TokenUsage(BaseModel):
    model_config = _RECORD

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    seconds: float = 0.0


class DecisionRecord(BaseModel):
    """One decision-model call, kept raw: its model version, tokens, seconds, answers."""

    model_config = _RECORD

    role: str
    model: str
    input_tokens: int
    seconds: float
    answers: dict[str, float]
    # The undecoded response body, as the backend stored it.
    raw: dict[str, Any] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    """A chunk the agent read, by its gold label and the sections it holds."""

    model_config = _RECORD

    chunk_id: str
    section_ids: list[str] = Field(default_factory=list)


class CitedSection(BaseModel):
    model_config = _RECORD

    index: int
    chunk_version_id: str
    chunk_id: str | None
    section_ids: list[str] = Field(default_factory=list)


class RoundRecord(BaseModel):
    """What the evidence held after one search round."""

    model_config = _RECORD

    sections: list[str]
    chunks: int
    # Characters of the evidence the answer step would read after this round.
    evidence_chars: int


class StepRecord(BaseModel):
    """One action of the agent loop: when it started and how long it took."""

    model_config = _RECORD

    kind: str
    outcome: str
    started_at: str
    seconds: float


class ReactRecord(BaseModel):
    """What a ReAct turn did with its search tool (the backend's ReactStats)."""

    model_config = _RECORD

    rounds: int = 0
    tool_calls: int = 0
    malformed_calls: int = 0
    duplicate_calls: int = 0
    round_cap_hit: bool = False
    # Answered without tools before the round cap because the LLM-call or token budget ran out.
    budget_forced: bool = False
    budget_hits: int = 0
    answered_without_search: bool = False


class ItemRecord(BaseModel):
    """A record about one golden item within one configuration."""

    model_config = _RECORD

    item_id: str
    config: str


class AnswerRecord(ItemRecord):
    status: str
    answer_mode: str | None = None
    answer_text: str = ""
    context_text: str = ""
    citations: list[CitedSection] = Field(default_factory=list)
    # Every chunk the final evidence set held, in rank order.
    retrieved: list[RetrievedChunk] = Field(default_factory=list)
    standalone_query: str = ""
    search_queries: list[list[str]] = Field(default_factory=list)
    rounds: list[RoundRecord] = Field(default_factory=list)
    judge_outcomes: list[str] = Field(default_factory=list)
    llm_calls: int = 0
    usage_by_role: dict[str, TokenUsage] = Field(default_factory=dict)
    # Every decision-model call of the turn (guard and judge) with its answers.
    decisions: list[DecisionRecord] = Field(default_factory=list)
    latency_seconds: float = 0.0
    # Wall time outside LLM calls: retrieval, reranking and graph overhead.
    non_llm_seconds: float = 0.0
    steps: list[StepRecord] = Field(default_factory=list)
    # Wall time of retrieval and rerank calls summed over the search rounds.
    retrieval_seconds: float = 0.0
    rerank_seconds: float = 0.0
    # Candidates the reranker scored over the turn (the priced rerank work).
    rerank_scored: int = 0
    # Set only for the react configuration.
    react: ReactRecord | None = None
    error: str | None = None
    retryable: bool = False

    @classmethod
    def failed(cls, item_id: str, config: str, error: BaseException) -> AnswerRecord:
        return cls(
            item_id=item_id,
            config=config,
            status="error",
            error=f"{type(error).__name__}: {error}"[:500],
            retryable=True,
        )

    @property
    def total_tokens(self) -> int:
        return sum(
            usage.prompt_tokens + usage.completion_tokens
            for usage in self.usage_by_role.values()
        )


class Judgement(ItemRecord):
    category: str
    # Legacy fields: `e2e report` recomputes these from the answers.
    behaviour_correct: bool | None = None
    injection_followed: bool | None = None
    declined: bool | None = None
    key_fact_verdicts: list[str] | None = None
    key_fact_recall: float | None = None
    contradiction: bool | None = None
    # none / minor / severe; judged only for answers that contradict a key fact.
    harm: str | None = None
    citation_precision: float | None = None
    citation_recall: float | None = None
    citation_support: float | None = None
    faithfulness: float | None = None
    factual_correctness: float | None = None
    answer_relevancy: float | None = None
    error: str | None = None


class JsonlStore[T: ItemRecord]:
    """Append-only records keyed by `item_id`; the last line for an item wins."""

    def __init__(self, path: Path, model: type[T]) -> None:
        self.path = Path(path)
        self._model = model

    def latest(self) -> dict[str, T]:
        records: dict[str, T] = {}
        if not self.path.is_file():
            return records
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = self._model.model_validate_json(line)
                    records[record.item_id] = record
        return records

    def append(self, record: T) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
