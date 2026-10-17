from typing import Any
from uuid import uuid4

import pytest
from langfuse import get_client
from openai.resources.embeddings import AsyncEmbeddings

from pharma_agent.application.chat.context import PipelineOptions
from pharma_agent.application.chat.runner import ChatTurnRunner
from pharma_agent.domain.agent.decisions import GuardThresholds
from pharma_agent.domain.llm.models import LlmRole
from pharma_agent.infrastructure.composition import (
    build_application,
    build_retrieval_service,
    guard_thresholds,
)
from pharma_agent.infrastructure.llm.openai_adapter import OpenAiLlmAdapter
from pharma_agent.infrastructure.llm.systemone_adapter import SystemOneAdapter
from pharma_agent.infrastructure.observability.langfuse_retrieval import (
    LangfuseTracedReranker,
)
from pharma_agent.infrastructure.persistence.postgres.database import Database
from pharma_agent.infrastructure.retrieval.llama_cpp_reranker import (
    NativeReranker,
    NoopReranker,
)
from pharma_agent.infrastructure.retrieval.postgres_corpus import PostgresCorpusReader
from pharma_agent.infrastructure.retrieval.qdrant_adapter import QdrantHybridRetriever
from pharma_agent.infrastructure.settings import LlmEndpoint, LlmSettings, Settings
from tests.fakes import FakeEmbedder


async def test_build_application_wires_real_adapters(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__API_KEY", "sk-test")
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__MODEL", "Qwen/Qwen3.5-9B")
    monkeypatch.setenv("PHARMA_SKILLS_DIR", str(tmp_path))
    monkeypatch.setenv("PHARMA_QDRANT__CHECK_COMPATIBILITY", "false")
    app = build_application(Settings(_env_file=None))
    assert isinstance(app.runner, ChatTurnRunner)
    assert app.runner.pipeline == PipelineOptions()
    assert isinstance(app.deps.llm, OpenAiLlmAdapter)
    assert isinstance(app.retrieval.retriever, QdrantHybridRetriever)
    assert isinstance(app.retrieval.reranker, NativeReranker)
    await app.aclose()


async def test_build_application_respects_rerank_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__API_KEY", "sk-test")
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__MODEL", "Qwen/Qwen3.5-9B")
    monkeypatch.setenv("PHARMA_RETRIEVAL__RERANK__PROTOCOL", "none")
    monkeypatch.setenv("PHARMA_SKILLS_DIR", str(tmp_path))
    monkeypatch.setenv("PHARMA_QDRANT__CHECK_COMPATIBILITY", "false")
    app = build_application(Settings(_env_file=None))
    assert isinstance(app.retrieval.reranker, NoopReranker)
    await app.aclose()


def test_build_application_requires_llm_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PHARMA_LLM__DEFAULT__API_KEY", raising=False)
    with pytest.raises(ValueError, match="api_key"):
        build_application(Settings(_env_file=None))


async def test_langfuse_traces_embeddings_and_rerank(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    public_key = f"pk-test-{uuid4().hex}"
    environment = {
        "PHARMA_LLM__DEFAULT__API_KEY": "sk-test",
        "PHARMA_LLM__DEFAULT__MODEL": "Qwen/Qwen3.5-9B",
        "PHARMA_SKILLS_DIR": str(tmp_path),
        "PHARMA_QDRANT__CHECK_COMPATIBILITY": "false",
        "PHARMA_LANGFUSE__PUBLIC_KEY": public_key,
        "PHARMA_LANGFUSE__SECRET_KEY": "sk-test",
        "PHARMA_LANGFUSE__HOST": "http://langfuse.test",
        # Set here so build_application's setdefault leaves them for monkeypatch to undo.
        "LANGFUSE_PUBLIC_KEY": public_key,
        "LANGFUSE_SECRET_KEY": "sk-test",
        "LANGFUSE_HOST": "http://langfuse.test",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    app = build_application(Settings(_env_file=None))

    assert isinstance(app.retrieval.reranker, LangfuseTracedReranker)
    # The Langfuse OpenAI integration is installed when the app is built, before any call.
    assert hasattr(AsyncEmbeddings.create, "__wrapped__")
    await app.aclose()
    get_client(public_key=public_key).shutdown()


async def test_build_retrieval_service_owns_its_database_unless_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHARMA_QDRANT__CHECK_COMPATIBILITY", "false")
    settings = Settings(_env_file=None)

    stack = build_retrieval_service(settings)
    assert isinstance(stack.retriever, QdrantHybridRetriever)
    assert isinstance(stack.reader, PostgresCorpusReader)
    assert stack.owns_database is True
    await stack.aclose()

    shared = Database(settings.postgres.dsn, pool_size=1)
    borrowed = build_retrieval_service(settings, database=shared)
    assert borrowed.database is shared and borrowed.owns_database is False
    await borrowed.aclose()
    await shared.dispose()


async def test_build_retrieval_service_uses_an_injected_embedder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHARMA_QDRANT__CHECK_COMPATIBILITY", "false")
    embedder = FakeEmbedder()

    stack = build_retrieval_service(Settings(_env_file=None), embedder=embedder)

    assert stack.embedder is embedder and stack.embed_client is None
    await stack.aclose()


def _decision_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path, roles: dict[LlmRole, LlmEndpoint]
) -> Settings:
    monkeypatch.setenv("PHARMA_SKILLS_DIR", str(tmp_path))
    monkeypatch.setenv("PHARMA_QDRANT__CHECK_COMPATIBILITY", "false")
    return Settings(
        _env_file=None,
        llm=LlmSettings(default=LlmEndpoint(api_key="k", model="m"), roles=roles),
    )


def _jev(extra_body: dict[str, Any] | None = None) -> LlmEndpoint:
    return LlmEndpoint(
        provider="systemone",
        base_url="https://openrouter.ai/api",
        api_key="or",
        model="~typesafe/jev-latest",
        extra_body=extra_body,
    )


async def test_decision_roles_get_the_systemone_adapter(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    settings = _decision_settings(monkeypatch, tmp_path, {LlmRole.JUDGE: _jev()})
    app = build_application(settings, embedder=FakeEmbedder())
    assert set(app.deps.decisions) == {LlmRole.JUDGE}
    assert isinstance(app.deps.decisions[LlmRole.JUDGE], SystemOneAdapter)
    await app.aclose()


async def test_no_decision_roles_means_no_decision_ports(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    settings = _decision_settings(monkeypatch, tmp_path, {})
    app = build_application(settings, embedder=FakeEmbedder())
    assert dict(app.deps.decisions) == {}
    await app.aclose()


async def test_guard_thresholds_come_from_the_guard_role_extra_body(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    guard = _jev({"thresholds": {"block": 0.8, "scope": 0.4}})
    settings = _decision_settings(monkeypatch, tmp_path, {LlmRole.GUARDRAIL: guard})
    app = build_application(settings, embedder=FakeEmbedder())
    assert app.deps.guardrail.thresholds == GuardThresholds(block=0.8, scope=0.4)
    await app.aclose()


async def test_guard_thresholds_stay_default_without_a_decision_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    other = LlmEndpoint(extra_body={"thresholds": {"block": 0.9}})
    settings = _decision_settings(monkeypatch, tmp_path, {LlmRole.GUARDRAIL: other})
    app = build_application(settings, embedder=FakeEmbedder())
    assert app.deps.guardrail.thresholds == GuardThresholds()
    await app.aclose()


def test_an_unknown_guard_threshold_key_is_refused() -> None:
    llm = LlmSettings(
        default=LlmEndpoint(api_key="k", model="m"),
        roles={LlmRole.GUARDRAIL: _jev({"thresholds": {"block": 0.8, "blok": 0.9}})},
    )
    with pytest.raises(ValueError, match="blok"):
        guard_thresholds(llm)
