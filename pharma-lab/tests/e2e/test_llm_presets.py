import json

import pytest
from pharma_agent.domain.llm.models import LlmRole

from pharma_lab.e2e.kernel_env import kernel_backend_env
from pharma_lab.e2e.llm_presets import PRESETS, preset_named


def env_for(name: str) -> dict[str, str]:
    return kernel_backend_env(
        llm_port=11434,
        rerank_port=11435,
        embedding_port=11436,
        postgres_dsn="postgresql+psycopg://v:v@127.0.0.1:5432/v",
        qdrant_url="http://127.0.0.1:6333",
        preset=PRESETS[name],
    )


def test_qwen_preset_env_is_byte_identical_to_current() -> None:
    default = kernel_backend_env(
        llm_port=11434,
        rerank_port=11435,
        embedding_port=11436,
        postgres_dsn="postgresql+psycopg://v:v@127.0.0.1:5432/v",
        qdrant_url="http://127.0.0.1:6333",
    )

    assert env_for("qwen") == default
    assert default["PHARMA_LLM__ROLES__AGENT__MODEL"] == "qwen3.5:9b-q8_0"
    assert default["PHARMA_LLM__DEFAULT__API_KEY"] == "kernel"
    assert not [k for k in default if k.startswith("PHARMA_LLM__DEFAULT__EXTRA")]
    assert len(default) == 15 + 4 * len(LlmRole)


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_every_llm_role_is_covered_by_every_preset(name: str) -> None:
    assert set(PRESETS[name].roles) == {role.name for role in LlmRole}
    values = env_for(name)
    for role in LlmRole:
        assert f"PHARMA_LLM__ROLES__{role.name}__MODEL" in values


@pytest.mark.parametrize("name", ["gemini", "opus"])
def test_proxy_presets_point_at_localhost_only(name: str) -> None:
    preset = PRESETS[name]
    values = env_for(name)

    assert preset.needs_proxy
    assert preset.providers
    urls = [v for k, v in values.items() if k.endswith("LLM__DEFAULT__BASE_URL")]
    urls += [
        v
        for k, v in values.items()
        if k.startswith("PHARMA_LLM__ROLES__") and k.endswith("BASE_URL")
    ]
    assert urls
    assert set(urls) == {"http://127.0.0.1:8317/v1"}
    assert values["PHARMA_LLM__DEFAULT__API_KEY"] == "proxypal-local"
    # Retrieval still runs on the kernel's own servers.
    assert values["PHARMA_RETRIEVAL__RERANK__BASE_URL"] == "http://127.0.0.1:11435"


def test_opus_sets_minimal_reasoning_effort() -> None:
    values = env_for("opus")

    assert values["PHARMA_LLM__ROLES__ANSWER__MODEL"] == "claude-opus-5-5"
    for role in LlmRole:
        assert values[f"PHARMA_LLM__ROLES__{role.name}__REASONING_EFFORT"] == "minimal"


def test_gemini_uses_its_model_and_no_qwen_body() -> None:
    values = env_for("gemini")

    assert values["PHARMA_LLM__ROLES__ANSWER__MODEL"] == "gemini-3.8-flash-high"
    assert "enable_thinking" not in json.dumps(values)


def test_qwen_needs_no_proxy() -> None:
    assert not PRESETS["qwen"].needs_proxy
    assert PRESETS["qwen"].providers == frozenset()


def test_unknown_preset_lists_the_valid_names() -> None:
    with pytest.raises(ValueError, match=r"gemini, opus, qwen"):
        preset_named("gpt")


def test_only_the_subscription_presets_have_a_request_ceiling() -> None:
    assert PRESETS["qwen"].max_in_flight is None
    gemini, opus = PRESETS["gemini"].max_in_flight, PRESETS["opus"].max_in_flight
    assert gemini is not None and opus is not None
    assert opus < gemini  # Claude has the lowest allowance


def test_gemini_uses_flash_lite_for_the_cheap_roles() -> None:
    values = env_for("gemini")

    for role in ("GUARDRAIL", "REPHRASE"):
        assert values[f"PHARMA_LLM__ROLES__{role}__MODEL"] == "gemini-3.1-flash-lite"
    for role in ("JUDGE", "REFINE", "ANSWER", "SUMMARIZER", "AGENT"):
        assert values[f"PHARMA_LLM__ROLES__{role}__MODEL"] == "gemini-3.8-flash-high"
