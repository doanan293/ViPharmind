"""Which LLM answers each role of the agent in a kernel run.

`qwen` is the llama-server inside the kernel. `gemini` and `opus` go through
`cli-proxy-api`, which the kernel starts on localhost with the user's credential files
(nothing is exposed outside the kernel). Pure values only: the kernel's orchestrating
process imports this module before the backend's dependencies are installed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

LLM_MODEL = "qwen3.5:9b-q8_0"
# Every role of the agent (LlmRole names); a test keeps the two in step.
LLM_ROLES = (
    "GUARDRAIL",
    "REPHRASE",
    "JUDGE",
    "REFINE",
    "ANSWER",
    "SUMMARIZER",
    "AGENT",
)
# Qwen3.5 thinks by default; the pipeline wants one structured decision per call.
CHAT_EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}
PROXY_BASE_URL = "http://127.0.0.1:8317/v1"
PROXY_API_KEY = "proxypal-local"
KERNEL_API_KEY = "kernel"


@dataclass(frozen=True)
class RoleEndpoint:
    """One role's endpoint; `base_url=None` is the kernel's own llama-server."""

    model: str
    api_key: str
    base_url: str | None = None
    extra_body: Mapping[str, object] = field(default_factory=dict)
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class LlmPreset:
    name: str
    roles: Mapping[str, RoleEndpoint]
    needs_proxy: bool
    # Credential types the proxy needs, e.g. {"antigravity"}; empty when none.
    providers: frozenset[str]
    # Requests a subscription lets us keep in flight at once, over every kernel of a
    # run (the Claude plan allows the fewest); None for the kernel's own server.
    max_in_flight: int | None = None


def _every_role(endpoint: RoleEndpoint) -> Mapping[str, RoleEndpoint]:
    return MappingProxyType(dict.fromkeys(LLM_ROLES, endpoint))


PRESETS: Mapping[str, LlmPreset] = MappingProxyType(
    {
        "qwen": LlmPreset(
            "qwen",
            _every_role(
                RoleEndpoint(LLM_MODEL, KERNEL_API_KEY, extra_body=CHAT_EXTRA_BODY)
            ),
            needs_proxy=False,
            providers=frozenset(),
        ),
        "gemini": LlmPreset(
            "gemini",
            _every_role(
                RoleEndpoint(
                    "gemini-3.8-flash-high", PROXY_API_KEY, base_url=PROXY_BASE_URL
                )
            ),
            needs_proxy=True,
            providers=frozenset({"antigravity"}),
            max_in_flight=4,
        ),
        "opus": LlmPreset(
            "opus",
            _every_role(
                RoleEndpoint(
                    "claude-opus-5-5",
                    PROXY_API_KEY,
                    base_url=PROXY_BASE_URL,
                    reasoning_effort="minimal",
                )
            ),
            needs_proxy=True,
            providers=frozenset({"claude"}),
            max_in_flight=2,
        ),
    }
)


def preset_named(name: str) -> LlmPreset:
    try:
        return PRESETS[name]
    except KeyError:
        raise ValueError(
            f"unknown LLM preset {name!r}; valid: {', '.join(sorted(PRESETS))}"
        ) from None
