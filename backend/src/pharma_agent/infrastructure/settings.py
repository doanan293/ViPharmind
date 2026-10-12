from typing import Any, Literal

from openai.types import ReasoningEffort
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from pharma_agent.domain.agent.budget import BudgetLimits
from pharma_agent.domain.llm.models import LlmRole

DEFAULT_ROLE_MODELS: dict[LlmRole, str] = {
    LlmRole.GUARDRAIL: "gpt-5-nano",
    LlmRole.REPHRASE: "gpt-5-nano",
    LlmRole.SUMMARIZER: "gpt-5-nano",
    LlmRole.JUDGE: "gpt-5-mini",
    LlmRole.REFINE: "gpt-5-mini",
    LlmRole.ANSWER: "gpt-5-mini",
}

# Applied only while a role runs its built-in model: these are reasoning models whose default
# effort ("medium") bills hidden reasoning tokens. Custom models get no reasoning_effort unless
# it is set explicitly, because many OpenAI-compatible servers reject the parameter.
DEFAULT_ROLE_REASONING: dict[LlmRole, ReasoningEffort] = {
    LlmRole.GUARDRAIL: "minimal",
    LlmRole.REPHRASE: "minimal",
    LlmRole.SUMMARIZER: "minimal",
    LlmRole.JUDGE: "low",
    LlmRole.REFINE: "low",
    LlmRole.ANSWER: "low",
}


class LlmEndpoint(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    reasoning_effort: ReasoningEffort = None
    # Provider-specific request fields passed as the OpenAI SDK's extra_body, e.g.
    # {"chat_template_kwargs": {"enable_thinking": false}} for Qwen on vLLM/DeepInfra.
    extra_body: dict[str, Any] | None = None


class ResolvedEndpoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: str | None
    api_key: str
    model: str
    reasoning_effort: ReasoningEffort = None
    extra_body: dict[str, Any] | None = None


class LlmSettings(BaseModel):
    default: LlmEndpoint = Field(default_factory=LlmEndpoint)
    roles: dict[LlmRole, LlmEndpoint] = Field(default_factory=dict)
    timeout_seconds: float = 60.0
    max_retries: int = 2

    @property
    def configured(self) -> bool:
        return bool(self.default.api_key) or all(
            (self.roles.get(role) or LlmEndpoint()).api_key for role in LlmRole
        )

    def resolve(self, role: LlmRole) -> ResolvedEndpoint:
        override = self.roles.get(role) or LlmEndpoint()
        api_key = override.api_key or self.default.api_key
        if not api_key:
            raise ValueError(
                f"no api_key for LLM role {role.value}: set PHARMA_LLM__DEFAULT__API_KEY"
            )
        model = override.model or self.default.model
        effort = override.reasoning_effort or self.default.reasoning_effort
        if model is None:
            model = DEFAULT_ROLE_MODELS[role]
            effort = effort or DEFAULT_ROLE_REASONING[role]
        return ResolvedEndpoint(
            base_url=override.base_url or self.default.base_url,
            api_key=api_key,
            model=model,
            reasoning_effort=effort,
            extra_body=override.extra_body or self.default.extra_body,
        )


class EmbeddingSettings(BaseModel):
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "llama"
    model: str = "qwen3-embedding:4b-fp16"
    dimension: int = 2560
    timeout_seconds: float = 60.0
    max_retries: int = Field(default=2, ge=0)


class RerankSettings(BaseModel):
    protocol: Literal["native_rerank", "deepinfra", "none"] = "native_rerank"
    base_url: str = "http://localhost:11435"
    api_key: str | None = None
    model: str = "qwen3-reranker:4b-fp16"
    top_n: int = 8
    # Candidates scored per search round, taken round-robin across queries by fused rank.
    # A single query (candidate_k=30) is scored in full, like the evaluation.
    max_candidates: int = Field(default=40, ge=1)
    timeout_seconds: float = 120.0
    # Concurrent /v1/rerank requests; each carries a whole search round (compose sets 1).
    max_concurrent: int = Field(default=2, ge=1)


class RetrievalSettings(BaseModel):
    # Alias of the physical collection chunks_<embedding model slug> (spec C §8.3).
    qdrant_collection: str = "chunks_current"
    # Scope of runs without a user (evaluation harness, CLI ask/check); each needs a
    # current release. Chat over the API searches what the signed-in user may see.
    collections: list[str] = Field(default_factory=lambda: ["formulary"])
    # bm25 = sparse only with no query embedding (evaluation baseline).
    mode: Literal["hybrid", "dense", "bm25"] = "hybrid"
    prefetch_k: int = 50
    rrf_k: int = 2
    candidate_k: int = 30
    hydrate_window: int = 1
    max_concurrent_searches: int = 3
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    rerank: RerankSettings = Field(default_factory=RerankSettings)


class QdrantSettings(BaseModel):
    url: str = "http://localhost:6333"
    api_key: str | None = None
    timeout_seconds: float = 30.0
    check_compatibility: bool = True
    # Applies when a collection is created: keeps dense vectors on disk instead of in RAM
    # (Qdrant Cloud's free tier has 1 GB of RAM).
    on_disk_vectors: bool = False


class LangfuseSettings(BaseModel):
    public_key: str | None = None
    secret_key: str | None = None
    host: str = "https://cloud.langfuse.com"

    @property
    def enabled(self) -> bool:
        return bool(self.public_key and self.secret_key)


class PostgresSettings(BaseModel):
    dsn: str = "postgresql+psycopg://vipharmind:vipharmind@localhost:5433/vipharmind"
    pool_size: int = 10
    echo: bool = False

    @property
    def conninfo(self) -> str:
        """libpq connection string for raw psycopg connections."""
        return self.dsn.replace("postgresql+psycopg://", "postgresql://", 1)


class AuthSettings(BaseModel):
    jwt_secret: SecretStr | None = None
    jwt_lifetime_seconds: int = 7 * 24 * 3600
    session_lifetime_seconds: int = Field(default=7 * 24 * 3600, ge=60)
    # Browsers accept Secure cookies on http://localhost, so this stays on in development.
    cookie_secure: bool = True
    csrf_secret: SecretStr | None = None
    otp_secret: SecretStr | None = None
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    frontend_url: str = "http://localhost:3000"

    @field_validator("jwt_secret", "csrf_secret", "otp_secret")
    @classmethod
    def _secret_length(
        cls, value: SecretStr | None, info: ValidationInfo
    ) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError(f"{info.field_name} must be at least 32 characters")
        return value

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    def require_jwt_secret(self) -> str:
        if self.jwt_secret is None:
            raise ValueError("set PHARMA_AUTH__JWT_SECRET (at least 32 characters)")
        return self.jwt_secret.get_secret_value()

    def require_otp_secret(self) -> str:
        if self.otp_secret is None:
            raise ValueError("set PHARMA_AUTH__OTP_SECRET (at least 32 characters)")
        return self.otp_secret.get_secret_value()

    def require_csrf_secret(self) -> str:
        if self.csrf_secret is None:
            raise ValueError("set PHARMA_AUTH__CSRF_SECRET (at least 32 characters)")
        return self.csrf_secret.get_secret_value()


class ApiSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    # The browser reaches the API on the same origin (nginx or the dev proxy): no CORS by default.
    cors_origins: list[str] = Field(default_factory=list)
    # Reverse proxies in front of the API that append to X-Forwarded-For (0 trusts none, so
    # per-IP limits use the TCP peer). Behind Render set 3.
    trusted_proxy_hops: int = Field(default=0, ge=0)
    # Shared with the frontend's /api proxy (API_PROXY_SECRET there): requests carrying it
    # in X-Vipharmind-Proxy count that proxy as one more trusted hop.
    proxy_secret: SecretStr | None = None


class MemorySettings(BaseModel):
    context_turns: int = 4
    context_chars: int = 4000
    summary_every_turns: int = 2
    summary_max_chars: int = 1500


class CorpusSettings(BaseModel):
    """Corpus import and release commands (spec C §8.2, §8.5)."""

    embed_batch_size: int = Field(default=32, ge=1)
    embed_max_concurrent: int = Field(default=1, ge=1)
    gc_keep: int = Field(default=2, ge=0)


class JobsSettings(BaseModel):
    """How publish jobs run (spec §5.3).

    `inprocess` runs them in the API process (local, tests); `inline` runs them inside the
    publish request (Vercel Functions, which may freeze after a response); `cloud_tasks`
    queues them on Google Cloud Tasks, which calls the backend back with an OIDC token.
    """

    dispatcher: Literal["inprocess", "inline", "cloud_tasks"] = "inprocess"
    # inprocess and inline: the X-Internal-Token header of /internal calls.
    internal_token: SecretStr | None = None
    # cloud_tasks: the public URL of the backend, used as target and OIDC audience.
    backend_url: str | None = None
    cloud_tasks_project: str | None = None
    cloud_tasks_location: str = "asia-southeast1"
    cloud_tasks_queue: str = "ingest"
    service_account_email: str | None = None
    max_attempts: int = Field(default=3, ge=1)
    dispatch_deadline_seconds: int = Field(default=600, ge=15, le=1800)


class QuotaSettings(BaseModel):
    """Default quotas of spec §2; users and organizations may override them in the DB."""

    document_chars: int = Field(default=200_000, ge=1)
    documents_per_collection: int = Field(default=100, ge=1)
    user_text_bytes: int = Field(default=1_000_000, ge=0)
    user_collections: int = Field(default=5, ge=0)
    org_text_bytes: int = Field(default=5_000_000, ge=0)
    org_collections: int = Field(default=20, ge=0)


class EmailSettings(BaseModel):
    """Where account emails go. `log` writes them to the log: local runs and tests only."""

    provider: Literal["log", "resend"] = "log"
    sender: str = "ViPharMind <no-reply@vipharmind.local>"
    resend_api_key: SecretStr | None = None
    timeout_seconds: float = Field(default=10.0, gt=0)


class SmsSettings(BaseModel):
    """`log` writes SMS to the log; `none` turns phone sign-in off (spec §2).

    A real provider is plugged in later; until then production runs with `none`.
    """

    provider: Literal["log", "none"] = "log"
    # ISO 3166 regions SMS may go to; anything else is rejected before sending.
    allowed_country_codes: list[str] = Field(default_factory=lambda: ["VN"])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PHARMA_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm: LlmSettings = Field(default_factory=LlmSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    budget: BudgetLimits = Field(default_factory=BudgetLimits)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)
    sms: SmsSettings = Field(default_factory=SmsSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    corpus: CorpusSettings = Field(default_factory=CorpusSettings)
    quotas: QuotaSettings = Field(default_factory=QuotaSettings)
    jobs: JobsSettings = Field(default_factory=JobsSettings)
    # Render and Cloud Run tell the container which port to listen on in PORT (no prefix).
    platform_port: int | None = Field(default=None, validation_alias="PORT")

    @model_validator(mode="after")
    def _listen_on_the_platform_port(self) -> "Settings":
        if self.platform_port is not None and "port" not in self.api.model_fields_set:
            self.api.port = self.platform_port
        return self
