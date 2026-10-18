"""DecisionPort over TypeSafe's SDK: POST /v1/systemone through OpenRouter (spec v2 §2.1b)."""

import time
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import ValidationError
from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy, TypeSafeError

from pharma_agent.domain.llm.decision import Decision, NoulQuestion
from pharma_agent.domain.llm.models import LlmRole
from pharma_agent.domain.llm.port import LlmError
from pharma_agent.infrastructure.settings import LlmSettings, ResolvedEndpoint

SystemOneClientFactory = Callable[[ResolvedEndpoint, float, float, int], Any]


def default_systemone_client(
    endpoint: ResolvedEndpoint, timeout: float, total: float, max_retries: int
) -> Any:
    """A client whose `timeout` bounds one request and `total` every attempt."""
    return AsyncTypeSafeClient(
        api_key=endpoint.api_key,
        base_url=endpoint.base_url,
        model=endpoint.model,
        timeout=timeout,
        retry=RetryPolicy(max_retries=max_retries, timeout=total),
    )


def question_payload(question: NoulQuestion) -> dict[str, object]:
    payload: dict[str, object] = {"type": "noul", "instructions": question.instructions}
    criteria = {
        k: v
        for k, v in (("true", question.true), ("false", question.false))
        if v is not None
    }
    if criteria:
        payload["criteria"] = criteria
    return payload


def raw_body(response: Any) -> dict[str, Any]:
    """The undecoded JSON body kept for answers.jsonl; empty when the SDK has none."""
    try:
        body = response.raw_http_response.json()
    except (TypeSafeError, ValueError, AttributeError):
        return {}
    return dict(body) if isinstance(body, Mapping) else {}


class SystemOneAdapter:
    def __init__(
        self,
        settings: LlmSettings,
        client_factory: SystemOneClientFactory = default_systemone_client,
    ) -> None:
        self._settings = settings
        self._factory = client_factory
        self._clients: dict[tuple[str | None, str], Any] = {}

    def endpoint(self, role: LlmRole) -> ResolvedEndpoint:
        endpoint = self._settings.resolve(role)
        if endpoint.provider != "systemone":
            raise LlmError(
                f"{role.value}: provider is {endpoint.provider}, not systemone"
            )
        return endpoint

    def _client(self, endpoint: ResolvedEndpoint) -> Any:
        key = (endpoint.base_url, endpoint.api_key)
        if key not in self._clients:
            self._clients[key] = self._factory(
                endpoint,
                self._settings.decision_timeout_seconds,
                self._settings.decision_total_seconds,
                self._settings.max_retries,
            )
        return self._clients[key]

    async def aclose(self) -> None:
        """Close every client the adapter opened."""
        clients, self._clients = list(self._clients.values()), {}
        for client in clients:
            close = getattr(client, "aclose", None)
            if close is not None:
                await close()

    async def decide(
        self,
        role: LlmRole,
        state: Mapping[str, object],
        questions: Mapping[str, NoulQuestion],
    ) -> Decision:
        endpoint = self.endpoint(role)
        client = self._client(endpoint)
        payload = {key: question_payload(q) for key, q in questions.items()}
        started = time.perf_counter()
        try:
            response = await client.system_one(
                dict(state), payload, model=endpoint.model
            )
        except Exception as exc:
            # Every SDK, HTTP or parse failure degrades like an LLM failure; an API
            # error's text carries its status and request id.
            raise LlmError(f"{role.value}: systemone request failed: {exc}") from exc
        seconds = time.perf_counter() - started
        answers = {key: probability(role, response, key) for key in questions}
        try:
            return Decision(
                answers=answers,
                model=str(response.model),
                input_tokens=int(getattr(response.usage, "input_tokens", 0) or 0),
                seconds=round(seconds, 4),
                raw=raw_body(response),
                request_id=request_id(response),
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise LlmError(
                f"{role.value}: malformed systemone response: {exc}"
            ) from exc


def request_id(response: Any) -> str | None:
    """The response's request id, for tracing a decision back to the provider."""
    try:
        return str(response.request_id)
    except (TypeSafeError, AttributeError):
        return None


def probability(role: LlmRole, response: Any, key: str) -> float:
    """The noul answer for `key` as a probability; anything else is an LlmError, so a
    malformed answer degrades like every other decision-model failure."""
    try:
        value = getattr(response.answers.get(key), "noul", None)
    except AttributeError as exc:
        raise LlmError(f"{role.value}: systemone answers are malformed: {exc}") from exc
    if value is None:
        raise LlmError(f"{role.value}: systemone answered without {key!r}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise LlmError(
            f"{role.value}: {key!r} is not a probability: {value!r}"
        ) from exc
    if not 0.0 <= number <= 1.0:  # also false for NaN
        raise LlmError(f"{role.value}: {key!r}={number} is outside [0, 1]")
    return number
