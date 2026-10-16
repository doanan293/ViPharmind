import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from pharma_agent import cli
from pharma_agent.api.app import create_app
from pharma_agent.api.openapi import openapi_export_settings, render_openapi
from pharma_agent.application.chat.graph import build_chat_graph
from pharma_agent.application.chat.runner import ChatTurnRunner
from pharma_agent.application.progress import EventType, ProgressEvent
from pharma_agent.domain.agent.budget import BudgetLimits
from pharma_agent.domain.agent.schemas import (
    Audience,
    Intent,
    JudgeDecision,
    JudgeOutcome,
    Language,
    RephraseResult,
)
from pharma_agent.domain.guardrail.models import LlmGuardVerdict
from pharma_agent.domain.llm.models import LlmRole
from pharma_agent.domain.retrieval.ports import RetrievalError
from pharma_agent.infrastructure.auth.session_cleanup import AccountCleanup
from pharma_agent.infrastructure.retrieval.llama_cpp_reranker import NoopReranker
from tests.domain.factories import make_hit
from tests.fakes import FakeLlm, FakeRetriever, build_deps


def fake_application() -> SimpleNamespace:
    llm = FakeLlm()
    llm.script(
        LlmRole.GUARDRAIL, LlmGuardVerdict(is_attack=False, in_scope=True, reason="ok")
    )
    llm.script(
        LlmRole.REPHRASE,
        RephraseResult(
            standalone_query="Liều paracetamol",
            audience=Audience.GENERAL_PUBLIC,
            language=Language.VI,
            intent=Intent.PHARMA_QUESTION,
        ),
    )
    llm.script(
        LlmRole.JUDGE,
        JudgeDecision(
            decision=JudgeOutcome.ANSWER, gaps=[], reason="đủ", confidence=1.0
        ),
    )
    deps = build_deps(llm, FakeRetriever([make_hit("c1", fusion=0.9)]))
    runner = ChatTurnRunner(build_chat_graph(), deps, BudgetLimits())

    async def aclose() -> None:
        return None

    return SimpleNamespace(runner=runner, aclose=aclose)


def test_ask_streams_answer_and_citations(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_application", lambda settings: fake_application())
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__API_KEY", "sk-test")
    result = CliRunner().invoke(cli.app, ["ask", "Paracetamol uống bao nhiêu?"])
    assert result.exit_code == 0, result.output
    assert "500 mg" in result.output
    assert "[1] Paracetamol > Liều dùng" in result.output
    assert "status: completed" in result.output


def test_ask_json_output(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_application", lambda settings: fake_application())
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__API_KEY", "sk-test")
    result = CliRunner().invoke(
        cli.app, ["ask", "Paracetamol uống bao nhiêu?", "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "completed" and payload["citations"][0]["index"] == 1
    assert payload["trace"]["usage"]["llm_calls"] == 4


def test_migrate_upgrades_to_head(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "alembic.command.upgrade",
        lambda config, revision: calls.append((config, revision)),
    )
    result = CliRunner().invoke(cli.app, ["migrate"])
    assert result.exit_code == 0, result.output
    config, revision = calls[0]
    assert revision == "head"
    assert config.get_main_option("script_location").endswith(":migrations")


def test_serve_runs_uvicorn_factory(monkeypatch) -> None:
    calls = {}
    monkeypatch.setattr(
        "uvicorn.run", lambda app, **kwargs: calls.update(app=app, **kwargs)
    )
    monkeypatch.setenv("PHARMA_API__PORT", "9001")
    result = CliRunner().invoke(cli.app, ["serve", "--host", "0.0.0.0"])
    assert result.exit_code == 0, result.output
    assert (
        calls["app"] == "pharma_agent.api.app:create_app" and calls["factory"] is True
    )
    assert (calls["host"], calls["port"]) == ("0.0.0.0", 9001)


def test_check_reports_corpus_embedding_and_rerank(monkeypatch) -> None:
    class Retriever:
        async def verify_corpus(self, *, embedding_model: str, dimension: int) -> None:
            raise RetrievalError(
                "0 of 1 collections in formulary have a current release"
            )

    class Embedder:
        async def embed(self, texts):
            return [[0.0] * 2560 for _ in texts]

    closed: list[bool] = []

    async def aclose() -> None:
        closed.append(True)

    stack = SimpleNamespace(
        retriever=Retriever(),
        embedder=Embedder(),
        reranker=NoopReranker(),
        aclose=aclose,
    )
    monkeypatch.setattr(cli, "build_retrieval_service", lambda settings: stack)
    result = CliRunner().invoke(cli.app, ["check"])
    assert result.exit_code == 1
    assert "ERR corpus: CORPUS_NOT_READY: 0 of 1 collections" in result.output
    assert "OK  embedding:" in result.output and "-> 2560 dims" in result.output
    assert "OK  rerank:" in result.output
    assert closed == [True]


def test_export_openapi_is_deterministic_and_matches_the_app(tmp_path: Path) -> None:
    nested, flat = tmp_path / "frontend" / "openapi.json", tmp_path / "openapi.json"
    for output in (nested, flat):
        result = CliRunner().invoke(
            cli.app, ["export-openapi", "--output", str(output)]
        )
        assert result.exit_code == 0, result.output
        assert f"wrote {output}" in result.output

    text = nested.read_text(encoding="utf-8")
    assert nested.read_bytes() == flat.read_bytes()
    assert text == render_openapi(create_app(openapi_export_settings()))
    assert text.endswith("\n")
    document = json.loads(text)
    assert list(document) == sorted(document)
    authorize = document["paths"]["/api/v1/auth/google/authorize"]["get"]
    assert authorize["operationId"] == "oauth:google.cookie.authorize"


def test_render_warns_when_the_turn_was_not_persisted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli._render(
        ProgressEvent(
            type=EventType.DONE, data={"status": "completed", "persisted": False}
        ),
        [],
    )
    assert "!! Không lưu được lượt hội thoại này." in capsys.readouterr().err

    cli._render(
        ProgressEvent(
            type=EventType.DONE, data={"status": "completed", "persisted": True}
        ),
        [],
    )
    assert capsys.readouterr().err == ""


def test_cleanup_sessions_uses_the_session_lifetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []

    async def fake_cleanup(
        conninfo: str, *, session_lifetime_seconds: int
    ) -> AccountCleanup:
        calls.append((conninfo, session_lifetime_seconds))
        return AccountCleanup(sessions=4, codes=2, rate_limit_buckets=3)

    monkeypatch.setattr(cli, "clean_account_tables", fake_cleanup)
    monkeypatch.setenv("PHARMA_AUTH__SESSION_LIFETIME_SECONDS", "3600")
    monkeypatch.setenv(
        "PHARMA_POSTGRES__DSN", "postgresql+psycopg://u:p@db.example:5432/app"
    )

    result = CliRunner().invoke(cli.app, ["cleanup-sessions"])

    assert result.exit_code == 0, result.output
    assert "deleted 4 sessions older than 3600 seconds" in result.output
    assert "deleted 2 codes and 3 rate limit buckets" in result.output
    assert calls == [("postgresql://u:p@db.example:5432/app", 3600)]


def test_env_file_option_feeds_every_command(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / "production.env"
    env_file.write_text(
        "PHARMA_POSTGRES__DSN=postgresql+psycopg://prod:secret@neon.example/vipharmind\n"
        "PHARMA_QDRANT__URL=https://qdrant.example\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("PHARMA_POSTGRES__DSN", raising=False)
    monkeypatch.delenv("PHARMA_QDRANT__URL", raising=False)
    upgrades = []
    monkeypatch.setattr(
        "alembic.command.upgrade",
        lambda config, revision: upgrades.append(config),
    )
    result = CliRunner().invoke(cli.app, ["--env-file", str(env_file), "migrate"])
    assert result.exit_code == 0, result.output
    assert "neon.example" in upgrades[0].attributes["dsn"]

    seen = []

    def stack(settings):
        seen.append(settings.qdrant.url)
        raise SystemExit(0)

    monkeypatch.setattr(cli, "build_retrieval_service", stack)
    CliRunner().invoke(cli.app, ["--env-file", str(env_file), "check"])
    assert seen == ["https://qdrant.example"]
