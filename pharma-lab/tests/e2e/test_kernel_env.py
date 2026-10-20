import json

from pharma_agent.domain.llm.models import LlmRole

from pharma_lab.e2e.kernel_env import LLM_ROLES, kernel_backend_env


def env() -> dict[str, str]:
    return kernel_backend_env(
        llm_port=11434,
        rerank_port=11435,
        embedding_port=11436,
        postgres_dsn="postgresql+psycopg://v:v@127.0.0.1:5432/v",
        qdrant_url="http://127.0.0.1:6333",
    )


def test_every_role_of_the_agent_is_listed() -> None:
    assert set(LLM_ROLES) == {role.name for role in LlmRole}


def test_every_role_runs_the_kernel_llm_without_thinking() -> None:
    values = env()

    for role in LLM_ROLES:
        prefix = f"PHARMA_LLM__ROLES__{role}__"
        assert values[prefix + "BASE_URL"] == "http://127.0.0.1:11434/v1"
        assert values[prefix + "MODEL"] == "qwen3.5:9b-q8_0"
        assert json.loads(values[prefix + "EXTRA_BODY"]) == {
            "chat_template_kwargs": {"enable_thinking": False}
        }
    assert values["PHARMA_LLM__TIMEOUT_SECONDS"] == "600"


def test_retrieval_points_at_the_kernel_servers_and_stores() -> None:
    values = env()

    assert values["PHARMA_RETRIEVAL__RERANK__PROTOCOL"] == "native_rerank"
    assert values["PHARMA_RETRIEVAL__RERANK__BASE_URL"] == "http://127.0.0.1:11435"
    assert values["PHARMA_RETRIEVAL__RERANK__MODEL"] == "qwen3-reranker:4b-q8_0"
    assert values["PHARMA_RETRIEVAL__EMBEDDING__BASE_URL"] == (
        "http://127.0.0.1:11436/v1"
    )
    assert values["PHARMA_RETRIEVAL__EMBEDDING__MODEL"] == "qwen3-embedding:4b-fp16"
    assert values["PHARMA_RETRIEVAL__EMBEDDING__DIMENSION"] == "2560"
    assert values["PHARMA_POSTGRES__DSN"].endswith("@127.0.0.1:5432/v")
    assert values["PHARMA_QDRANT__URL"] == "http://127.0.0.1:6333"
