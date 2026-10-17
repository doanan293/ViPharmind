import json
from pathlib import Path

import pytest
from pharma_agent.application.chat.context import PipelineOptions
from pharma_agent.domain.agent.schemas import JudgeDecision, JudgeOutcome
from pharma_agent.domain.llm.models import LlmRole
from pharma_agent.infrastructure.settings import (
    LlmEndpoint,
    LlmSettings,
    Settings,
)
from tests.e2e.factories import ScriptedLlm

from pharma_lab.e2e.configs import (
    E2EConfig,
    config_label,
    graph_for,
    parse_pipeline_options,
    pipeline_for,
    settings_for,
)
from pharma_lab.e2e.harness import DecisionVersionGuard
from pharma_lab.e2e.recording_llm import RecordingLlm
from pharma_lab.e2e.records import AnswerRecord, DecisionRecord, JsonlStore, TokenUsage
from pharma_lab.e2e.run_identity import (
    RunIdentity,
    identity_from_settings,
    open_run,
)


def base_settings() -> Settings:
    return Settings(
        _env_file=None,
        langfuse={"public_key": "pk", "secret_key": "sk"},
        llm={"default": {"api_key": "sk-test", "model": "Qwen/Qwen3.5-9B"}},
    )


def test_configs_map_to_pipelines_and_settings() -> None:
    assert pipeline_for(E2EConfig.ONE_STEP) == PipelineOptions(
        rephrase=False, judge_refine=False
    )
    assert pipeline_for(E2EConfig.NO_RERANK) == PipelineOptions()
    base = base_settings()

    no_rerank = settings_for(base, E2EConfig.NO_RERANK)
    full = settings_for(base, E2EConfig.FULL)

    assert no_rerank.retrieval.rerank.protocol == "none"
    assert full.retrieval.rerank.protocol == "native_rerank"
    assert not full.langfuse.enabled
    assert base.langfuse.enabled
    assert base.retrieval.rerank.protocol == "native_rerank"


def test_store_keeps_the_last_record_per_item(tmp_path: Path) -> None:
    store = JsonlStore(tmp_path / "answers.jsonl", AnswerRecord)
    assert store.latest() == {}
    store.append(AnswerRecord.failed("a", "full", RuntimeError("boom")))
    store.append(AnswerRecord(item_id="b", config="full", status="completed"))
    store.append(AnswerRecord(item_id="a", config="full", status="completed"))

    latest = store.latest()

    assert sorted(latest) == ["a", "b"]
    assert latest["a"].status == "completed"
    assert not latest["a"].retryable
    assert len((tmp_path / "answers.jsonl").read_text("utf-8").splitlines()) == 3


def test_failed_record_is_retryable_and_short() -> None:
    record = AnswerRecord.failed("a", "full", ValueError("x" * 1000))
    assert record.retryable
    assert record.error is not None and len(record.error) == 500
    assert record.error.startswith("ValueError: ")


def test_total_tokens_sums_roles() -> None:
    record = AnswerRecord(
        item_id="a",
        config="full",
        status="completed",
        usage_by_role={
            "answer": TokenUsage(calls=1, prompt_tokens=100, completion_tokens=20),
            "judge": TokenUsage(calls=1, prompt_tokens=10, completion_tokens=2),
        },
    )
    assert record.total_tokens == 132


async def test_recording_llm_counts_calls_per_role() -> None:
    inner = ScriptedLlm()
    decision = JudgeDecision(
        decision=JudgeOutcome.ANSWER, gaps=[], reason="ok", confidence=1.0
    )
    inner.script(LlmRole.JUDGE, decision, decision)
    llm = RecordingLlm(inner)

    await llm.structured(LlmRole.JUDGE, [], JudgeDecision)
    await llm.structured(LlmRole.JUDGE, [], JudgeDecision)
    text = "".join([delta.text async for delta in llm.stream(LlmRole.ANSWER, [])])

    assert text == "Trả lời [1]."
    usage = llm.usage_by_role()
    assert usage["judge"].model_copy(update={"seconds": 0.0}) == TokenUsage(
        calls=2, prompt_tokens=20, completion_tokens=4
    )
    assert usage["answer"].model_copy(update={"seconds": 0.0}) == TokenUsage(
        calls=1, prompt_tokens=100, completion_tokens=20
    )
    assert all(entry.seconds >= 0 for entry in usage.values())


def identity(settings: Settings, **changes: str) -> RunIdentity:
    values = {"golden_sha256": "g" * 64, "config": "full", "release_id": "r1"}
    values.update(changes)
    return identity_from_settings(
        settings,
        pipeline={"rephrase": True, "judge_refine": True},
        **values,
    )


def test_identity_records_models_without_secrets() -> None:
    settings = base_settings()
    current = identity(settings)
    assert current.role_models["answer"] == {
        "model": "Qwen/Qwen3.5-9B",
        "reasoning_effort": None,
        "provider": "openai",
    }
    assert current.rerank["protocol"] == "native_rerank"
    assert "sk-test" not in json.dumps(current.__dict__)


def test_identity_records_extra_body_only_when_set() -> None:
    settings = Settings(
        _env_file=None,
        langfuse={"public_key": "pk", "secret_key": "sk"},
        llm={
            "default": {"api_key": "sk-test", "model": "Qwen/Qwen3.5-9B"},
            "roles": {
                "answer": {
                    "model": "Qwen/Qwen3.5-9B",
                    "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
                }
            },
        },
    )
    current = identity(settings)
    assert current.role_models["answer"] == {
        "model": "Qwen/Qwen3.5-9B",
        "reasoning_effort": None,
        "provider": "openai",
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }
    assert "extra_body" not in current.role_models["judge"]


def test_identity_records_output_cap_only_when_set() -> None:
    settings = Settings(
        _env_file=None,
        langfuse={"public_key": "pk", "secret_key": "sk"},
        llm={
            "default": {"api_key": "sk-test", "model": "Qwen/Qwen3.5-9B"},
            "roles": {"judge": {"max_output_tokens": 512}},
        },
    )
    current = identity(settings)
    assert current.role_models["judge"]["max_output_tokens"] == 512
    assert "max_output_tokens" not in current.role_models["answer"]


def test_open_run_resumes_only_the_same_identity(tmp_path: Path) -> None:
    settings = base_settings()
    open_run(tmp_path, identity(settings), commit="abc")
    stored = json.loads((tmp_path / "run.json").read_text("utf-8"))
    assert stored["git_commit"] == "abc"

    open_run(tmp_path, identity(settings), commit="def")
    with pytest.raises(ValueError, match=r"\(release_id\); start a new --run"):
        open_run(tmp_path, identity(settings, release_id="r2"), commit="abc")


def test_pipeline_options_parse_and_label() -> None:
    options = parse_pipeline_options(PipelineOptions(), ["guard=false"])
    assert options == PipelineOptions(guard=False)
    assert config_label(E2EConfig.FULL, ["guard=false"]) == "full+guard=false"
    assert config_label(E2EConfig.FULL, []) == "full"


def test_unknown_pipeline_option_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown pipeline option 'rerank'"):
        parse_pipeline_options(PipelineOptions(), ["rerank=false"])
    with pytest.raises(ValueError, match="guard"):
        parse_pipeline_options(PipelineOptions(), ["guard=maybe"])
    with pytest.raises(ValueError, match="key=value"):
        parse_pipeline_options(PipelineOptions(), ["guard"])


def test_retriever_variants_change_only_retrieval_settings() -> None:
    base = base_settings()
    assert settings_for(base, E2EConfig.BM25).retrieval.mode == "bm25"
    assert settings_for(base, E2EConfig.DENSE).retrieval.mode == "dense"
    k60 = settings_for(base, E2EConfig.HYBRID_K60).retrieval
    assert (k60.mode, k60.rrf_k) == ("hybrid", 60)
    assert pipeline_for(E2EConfig.NO_GUARD) == PipelineOptions(guard=False)
    assert pipeline_for(E2EConfig.BM25) == PipelineOptions()


def test_concurrency_is_recorded_but_may_change_on_resume(tmp_path: Path) -> None:
    identity = identity_from_settings(
        base_settings(), golden_sha256="g", config="full", pipeline={}, release_id="r"
    )
    open_run(tmp_path, identity, commit="c", extra={"concurrency": 4})
    open_run(tmp_path, identity, commit="c", extra={"concurrency": 1})
    stored = json.loads((tmp_path / "run.json").read_text("utf-8"))
    assert stored["concurrency"] == 4


def test_identity_records_the_provider_per_role() -> None:
    settings = base_settings().model_copy(
        update={
            "llm": LlmSettings(
                default=LlmEndpoint(api_key="k", model="m"),
                roles={
                    LlmRole.GUARDRAIL: LlmEndpoint(
                        provider="systemone",
                        base_url="https://openrouter.ai/api",
                        api_key="or",
                        model="~typesafe/jev-latest",
                    )
                },
            )
        }
    )
    current = identity_from_settings(
        settings, golden_sha256="g", config="full", pipeline={}, release_id="r"
    )
    assert current.role_models["guardrail"]["provider"] == "systemone"
    assert current.role_models["answer"]["provider"] == "openai"


def _decision(model: str) -> DecisionRecord:
    return DecisionRecord(
        role="judge", model=model, input_tokens=1, seconds=0.1, answers={}
    )


def test_run_stops_when_the_decision_model_version_changes(tmp_path: Path) -> None:
    identity = identity_from_settings(
        base_settings(), golden_sha256="g", config="full", pipeline={}, release_id="r"
    )
    open_run(tmp_path, identity, commit="c")
    guard = DecisionVersionGuard(tmp_path)
    guard.observe([_decision("jev-1.13.0")])
    guard.observe([_decision("jev-1.13.0")])
    with pytest.raises(ValueError, match=r"jev-1\.13\.0 to jev-1\.14\.0"):
        guard.observe([_decision("jev-1.14.0")])
    stored = json.loads((tmp_path / "run.json").read_text("utf-8"))
    assert stored["decision_model_version"] == "jev-1.13.0"
    # A fresh guard on the same directory (a resume) still knows the version.
    with pytest.raises(ValueError, match=r"jev-1\.13\.0 to jev-1\.14\.0"):
        DecisionVersionGuard(tmp_path).observe([_decision("jev-1.14.0")])
    # The recorded version is informational, so the identity still resumes.
    open_run(tmp_path, identity, commit="c")


def test_react_config_selects_the_react_graph() -> None:
    assert pipeline_for(E2EConfig.REACT) == PipelineOptions()
    assert graph_for(E2EConfig.REACT).get_graph().nodes.keys() >= {
        "guard",
        "agent",
        "tools",
        "finalize",
    }
    assert "rephrase" in graph_for(E2EConfig.FULL).get_graph().nodes
