import pytest
from pydantic import ValidationError

from pharma_agent.domain.llm.models import LlmRole
from pharma_agent.infrastructure.settings import Settings


def test_defaults_match_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__API_KEY", "sk-test")
    monkeypatch.delenv("PHARMA_LLM__DEFAULT__MODEL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.retrieval.qdrant_collection == "chunks_current"
    assert settings.retrieval.collections == ["formulary"]
    assert settings.retrieval.mode == "hybrid"
    assert settings.retrieval.embedding.model == "qwen3-embedding:4b-q8_0"
    assert settings.retrieval.embedding.dimension == 2560
    assert (
        settings.retrieval.prefetch_k,
        settings.retrieval.rrf_k,
        settings.retrieval.candidate_k,
    ) == (50, 2, 20)
    assert settings.retrieval.rerank.protocol == "native_rerank"
    assert settings.retrieval.rerank.model == "qwen3-reranker:4b-q8_0"
    assert (
        settings.budget.max_llm_calls == 10 and settings.budget.deadline_seconds == 90
    )
    # No built-in model: a role without one fails at startup instead of guessing.
    with pytest.raises(ValueError, match="PHARMA_LLM__ROLES__ANSWER__MODEL"):
        settings.llm.resolve(LlmRole.ANSWER)
    assert settings.langfuse.enabled is False
    assert settings.jobs.stale_after_seconds == 330


def test_role_override_and_nested_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__API_KEY", "sk-cloud")
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__MODEL", "Qwen/Qwen3.5-9B")
    monkeypatch.setenv(
        "PHARMA_LLM__ROLES__ANSWER__BASE_URL", "http://localhost:8000/v1"
    )
    monkeypatch.setenv("PHARMA_LLM__ROLES__ANSWER__API_KEY", "local")
    monkeypatch.setenv("PHARMA_LLM__ROLES__ANSWER__MODEL", "qwen3-8b")
    monkeypatch.setenv("PHARMA_RETRIEVAL__RERANK__PROTOCOL", "none")
    monkeypatch.setenv("PHARMA_QDRANT__URL", "http://qdrant:6333")
    monkeypatch.setenv("PHARMA_RETRIEVAL__COLLECTIONS", '["formulary", "leaflets"]')
    monkeypatch.setenv("PHARMA_RETRIEVAL__MODE", "bm25")
    settings = Settings(_env_file=None)
    answer = settings.llm.resolve(LlmRole.ANSWER)
    assert (answer.base_url, answer.api_key, answer.model) == (
        "http://localhost:8000/v1",
        "local",
        "qwen3-8b",
    )
    judge = settings.llm.resolve(LlmRole.JUDGE)
    assert (judge.base_url, judge.api_key, judge.model) == (
        None,
        "sk-cloud",
        "Qwen/Qwen3.5-9B",
    )
    assert settings.retrieval.rerank.protocol == "none"
    assert settings.qdrant.url == "http://qdrant:6333"
    assert settings.retrieval.collections == ["formulary", "leaflets"]
    assert settings.retrieval.mode == "bm25"


def test_missing_api_key_means_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PHARMA_LLM__DEFAULT__API_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert settings.llm.configured is False
    with pytest.raises(ValueError, match="api_key"):
        settings.llm.resolve(LlmRole.ANSWER)


def test_platform_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("PHARMA_AUTH__JWT_SECRET", "PHARMA_POSTGRES__DSN"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert (
        settings.postgres.dsn
        == "postgresql+psycopg://vipharmind:vipharmind@localhost:5433/vipharmind"
    )
    assert (
        settings.postgres.conninfo
        == "postgresql://vipharmind:vipharmind@localhost:5433/vipharmind"
    )
    assert settings.memory.summary_every_turns == 2
    assert settings.memory.context_turns == 4
    assert settings.auth.google_enabled is False
    with pytest.raises(ValueError, match="PHARMA_AUTH__JWT_SECRET"):
        settings.auth.require_jwt_secret()


def test_auth_secret_and_google(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMA_AUTH__JWT_SECRET", "x" * 40)
    monkeypatch.setenv("PHARMA_AUTH__GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("PHARMA_AUTH__GOOGLE_CLIENT_SECRET", "secret")
    settings = Settings(_env_file=None)
    assert settings.auth.require_jwt_secret() == "x" * 40
    assert settings.auth.google_enabled is True


def test_short_jwt_secret_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMA_AUTH__JWT_SECRET", "short")
    with pytest.raises(ValueError, match="at least 32"):
        Settings(_env_file=None)


def test_reasoning_effort_is_sent_only_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__API_KEY", "sk-cloud")
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__MODEL", "Qwen/Qwen3.5-9B")
    monkeypatch.setenv("PHARMA_LLM__ROLES__JUDGE__REASONING_EFFORT", "medium")
    settings = Settings(_env_file=None)
    assert settings.llm.resolve(LlmRole.GUARDRAIL).reasoning_effort is None
    assert settings.llm.resolve(LlmRole.JUDGE).reasoning_effort == "medium"
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__REASONING_EFFORT", "low")
    settings = Settings(_env_file=None)
    assert settings.llm.resolve(LlmRole.ANSWER).reasoning_effort == "low"
    assert settings.llm.resolve(LlmRole.JUDGE).reasoning_effort == "medium"


def test_a_role_override_supplies_its_own_model() -> None:
    settings = Settings(
        _env_file=None,
        llm={"default": {"api_key": "sk"}, "roles": {"answer": {"model": "big"}}},
    )
    assert settings.llm.resolve(LlmRole.ANSWER).model == "big"
    with pytest.raises(ValueError, match="no model for LLM role judge"):
        settings.llm.resolve(LlmRole.JUDGE)


def test_role_extra_body_is_read_from_json_and_inherits_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__API_KEY", "sk-cloud")
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__MODEL", "Qwen/Qwen3.5-9B")
    monkeypatch.setenv(
        "PHARMA_LLM__DEFAULT__EXTRA_BODY", '{"chat_template_kwargs": {"x": 1}}'
    )
    monkeypatch.setenv(
        "PHARMA_LLM__ROLES__ANSWER__EXTRA_BODY",
        '{"chat_template_kwargs": {"enable_thinking": false}}',
    )
    settings = Settings(_env_file=None)
    assert settings.llm.resolve(LlmRole.ANSWER).extra_body == {
        "chat_template_kwargs": {"enable_thinking": False}
    }
    assert settings.llm.resolve(LlmRole.JUDGE).extra_body == {
        "chat_template_kwargs": {"x": 1}
    }


def test_extra_body_is_unset_by_default() -> None:
    settings = Settings(
        _env_file=None, llm={"default": {"api_key": "sk", "model": "m"}}
    )
    assert settings.llm.resolve(LlmRole.ANSWER).extra_body is None


def test_output_cap_is_read_per_role_and_inherits_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__API_KEY", "sk")
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__MODEL", "m")
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__MAX_OUTPUT_TOKENS", "4096")
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__MAX_TOKENS_PARAM", "max_tokens")
    monkeypatch.setenv("PHARMA_LLM__ROLES__JUDGE__MAX_OUTPUT_TOKENS", "512")
    settings = Settings(_env_file=None)
    judge = settings.llm.resolve(LlmRole.JUDGE)
    answer = settings.llm.resolve(LlmRole.ANSWER)
    assert (judge.max_output_tokens, judge.max_tokens_param) == (512, "max_tokens")
    assert (answer.max_output_tokens, answer.max_tokens_param) == (4096, "max_tokens")


def test_output_cap_is_unset_by_default() -> None:
    settings = Settings(
        _env_file=None, llm={"default": {"api_key": "sk", "model": "m"}}
    )
    endpoint = settings.llm.resolve(LlmRole.ANSWER)
    assert endpoint.max_output_tokens is None
    assert endpoint.max_tokens_param == "max_completion_tokens"


def test_embedding_and_rerank_connection_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = Settings(_env_file=None).retrieval
    assert (defaults.embedding.timeout_seconds, defaults.embedding.max_retries) == (
        60.0,
        2,
    )
    assert defaults.rerank.api_key is None
    assert (defaults.rerank.max_candidates, defaults.rerank.max_concurrent) == (40, 2)

    monkeypatch.setenv("PHARMA_RETRIEVAL__EMBEDDING__TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("PHARMA_RETRIEVAL__EMBEDDING__MAX_RETRIES", "0")
    monkeypatch.setenv("PHARMA_RETRIEVAL__RERANK__API_KEY", "rerank-secret")
    monkeypatch.setenv("PHARMA_RETRIEVAL__RERANK__MAX_CANDIDATES", "20")
    configured = Settings(_env_file=None).retrieval
    assert (configured.embedding.timeout_seconds, configured.embedding.max_retries) == (
        5.0,
        0,
    )
    assert configured.rerank.api_key == "rerank-secret"
    assert configured.rerank.max_candidates == 20


def test_corpus_settings_defaults_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    corpus = Settings(_env_file=None).corpus
    assert (corpus.embed_batch_size, corpus.embed_max_concurrent, corpus.gc_keep) == (
        32,
        1,
        2,
    )
    monkeypatch.setenv("PHARMA_CORPUS__EMBED_MAX_CONCURRENT", "4")
    monkeypatch.setenv("PHARMA_CORPUS__GC_KEEP", "0")
    configured = Settings(_env_file=None).corpus
    assert (configured.embed_max_concurrent, configured.gc_keep) == (4, 0)
    monkeypatch.setenv("PHARMA_CORPUS__EMBED_BATCH_SIZE", "0")
    with pytest.raises(ValueError, match="embed_batch_size"):
        Settings(_env_file=None)


def test_session_cookie_and_csrf_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "PHARMA_AUTH__CSRF_SECRET",
        "PHARMA_AUTH__COOKIE_SECURE",
        "PHARMA_AUTH__SESSION_LIFETIME_SECONDS",
        "PHARMA_API__CORS_ORIGINS",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.auth.session_lifetime_seconds == 604800
    assert settings.auth.cookie_secure is True
    assert settings.api.cors_origins == []
    with pytest.raises(ValueError, match="PHARMA_AUTH__CSRF_SECRET"):
        settings.auth.require_csrf_secret()


def test_csrf_secret_and_cookie_flags_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMA_AUTH__CSRF_SECRET", "c" * 40)
    monkeypatch.setenv("PHARMA_AUTH__COOKIE_SECURE", "false")
    monkeypatch.setenv("PHARMA_AUTH__SESSION_LIFETIME_SECONDS", "3600")
    monkeypatch.setenv("PHARMA_API__CORS_ORIGINS", '["http://localhost:5173"]')
    settings = Settings(_env_file=None)
    assert settings.auth.require_csrf_secret() == "c" * 40
    assert settings.auth.cookie_secure is False
    assert settings.auth.session_lifetime_seconds == 3600
    assert settings.api.cors_origins == ["http://localhost:5173"]


def test_short_csrf_secret_and_tiny_session_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHARMA_AUTH__CSRF_SECRET", "short")
    with pytest.raises(ValueError, match="csrf_secret must be at least 32"):
        Settings(_env_file=None)
    monkeypatch.delenv("PHARMA_AUTH__CSRF_SECRET")
    monkeypatch.setenv("PHARMA_AUTH__SESSION_LIFETIME_SECONDS", "10")
    with pytest.raises(ValueError, match="session_lifetime_seconds"):
        Settings(_env_file=None)


def test_rerank_protocol_rejects_completion_logprobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHARMA_LLM__DEFAULT__API_KEY", "sk-test")
    monkeypatch.setenv("PHARMA_RETRIEVAL__RERANK__PROTOCOL", "completion_logprobs")

    with pytest.raises(ValidationError, match="protocol"):
        Settings(_env_file=None)


def test_account_settings_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.email.provider == "log"
    assert settings.email.resend_api_key is None
    assert settings.sms.provider == "log"
    assert settings.sms.allowed_country_codes == ["VN"]
    assert settings.auth.otp_secret is None
    with pytest.raises(ValueError, match="PHARMA_AUTH__OTP_SECRET"):
        settings.auth.require_otp_secret()


def test_otp_secret_needs_32_characters() -> None:
    with pytest.raises(ValidationError, match="otp_secret"):
        Settings(_env_file=None, auth={"otp_secret": "short"})
    settings = Settings(_env_file=None, auth={"otp_secret": "o" * 32})
    assert settings.auth.require_otp_secret() == "o" * 32


def test_email_and_sms_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMA_EMAIL__PROVIDER", "resend")
    monkeypatch.setenv("PHARMA_EMAIL__RESEND_API_KEY", "re_test")
    monkeypatch.setenv("PHARMA_SMS__ALLOWED_COUNTRY_CODES", '["VN", "US"]')
    settings = Settings(_env_file=None)
    assert settings.email.provider == "resend"
    key = settings.email.resend_api_key
    assert key is not None and key.get_secret_value() == "re_test"
    assert settings.sms.allowed_country_codes == ["VN", "US"]


def test_jobs_can_run_inline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMA_JOBS__DISPATCHER", "inline")
    monkeypatch.setenv("PHARMA_JOBS__STALE_AFTER_SECONDS", "900")
    jobs = Settings(_env_file=None).jobs
    assert (jobs.dispatcher, jobs.stale_after_seconds) == ("inline", 900)
