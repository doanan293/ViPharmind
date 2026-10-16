from __future__ import annotations

import json
import math
import time
from collections.abc import Callable

import requests


class LlamaCppError(RuntimeError):
    pass


class LlamaCppRequestError(LlamaCppError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        failed_input_index: int | None = None,
        context_size: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.failed_input_index = failed_input_index
        # Set when the server refused an input longer than its context per slot.
        self.context_size = context_size


class LlamaCppResponseError(LlamaCppError):
    pass


# llama.cpp answers HTTP 500 when a prompt does not fit the physical batch. The same
# input fails again on a fresh server, so such a response must never be retried: on
# Kaggle a retry costs a server lifetime and, after the restarts, a whole GPU session.
INPUT_TOO_LARGE = "is too large to process"
# llama.cpp answers HTTP 400 with this error type when an input is longer than the context
# per slot, which it caps at the model's training context (EmbeddingGemma: 2,048 tokens).
EXCEED_CONTEXT_SIZE = "exceed_context_size_error"

EmbeddingInput = str | list[int]


def _context_size(body: str) -> int | None:
    try:
        error = json.loads(body).get("error")
    except (ValueError, AttributeError):
        return None
    if not isinstance(error, dict) or error.get("type") != EXCEED_CONTEXT_SIZE:
        return None
    n_ctx = error.get("n_ctx")
    return n_ctx if isinstance(n_ctx, int) and n_ctx > 0 else None


class LlamaCppClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 900.0,
        post: Callable = requests.post,
        get: Callable = requests.get,
        max_attempts: int = 3,
        retry_delay_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self._post = post
        self._get = get
        self.max_attempts = max(1, max_attempts)
        self.retry_delay_seconds = max(0.0, float(retry_delay_seconds))
        self._sleep = sleep

    def health(self) -> None:
        url = f"{self.base_url}/health"
        try:
            response = self._get(url, timeout=min(self.timeout, 10.0))
            response.raise_for_status()
        except Exception as exc:
            raise LlamaCppRequestError(
                f"llama.cpp health request failed: {url}: {exc}"
            ) from exc

    def embed(
        self, texts: list[str], model: str, expected_dimension: int
    ) -> list[list[float]]:
        if not texts:
            return []
        last_error = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self._embed_once(texts, model, expected_dimension)
            except LlamaCppRequestError as exc:
                if exc.context_size is not None:
                    inputs = [
                        self._fit_context(text, exc.context_size) for text in texts
                    ]
                    return self._embed_once(inputs, model, expected_dimension)
                last_error = exc
                if not exc.retryable or attempt >= self.max_attempts:
                    break
                self._sleep(self.retry_delay_seconds * attempt)
        assert last_error is not None
        if last_error.retryable and len(texts) > 1:
            midpoint = len(texts) // 2
            try:
                left = self.embed(texts[:midpoint], model, expected_dimension)
            except LlamaCppRequestError as exc:
                if exc.failed_input_index is None:
                    exc.failed_input_index = 0
                raise
            try:
                right = self.embed(texts[midpoint:], model, expected_dimension)
            except LlamaCppRequestError as exc:
                if exc.failed_input_index is None:
                    exc.failed_input_index = 0
                exc.failed_input_index += midpoint
                raise
            return left + right
        if last_error.failed_input_index is None and len(texts) == 1:
            last_error.failed_input_index = 0
        raise last_error

    def _tokenize(self, text: str, *, add_special: bool) -> list[int]:
        tokens = self._request(
            "/tokenize", {"content": text, "add_special": add_special}
        ).get("tokens")
        if not isinstance(tokens, list) or not all(
            isinstance(token, int) for token in tokens
        ):
            raise LlamaCppResponseError("Tokenize response has no token list")
        return tokens

    def _fit_context(self, text: str, context_size: int) -> EmbeddingInput:
        """Keep the head of a text longer than the server context, as sentence-transformers
        truncates at max_seq_length; the model's special tokens stay at both ends."""
        tokens = self._tokenize(text, add_special=True)
        if len(tokens) <= context_size:
            return text
        content = self._tokenize(text, add_special=False)
        prefix = next(
            (
                start
                for start in range(len(tokens) - len(content) + 1)
                if tokens[start : start + len(content)] == content
            ),
            None,
        )
        if prefix is None:
            raise LlamaCppResponseError(
                "Tokenize with special tokens does not contain the plain tokens"
            )
        head = tokens[:prefix]
        tail = tokens[prefix + len(content) :]
        room = context_size - len(head) - len(tail)
        if room < 1:
            raise LlamaCppResponseError(
                f"Context of {context_size} tokens has no room for content"
            )
        return [*head, *content[:room], *tail]

    def _embed_once(
        self,
        texts: list[str] | list[EmbeddingInput],
        model: str,
        expected_dimension: int,
    ) -> list[list[float]]:
        payload = self._request(
            "/v1/embeddings", {"model": model, "input": list(texts)}
        )
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise LlamaCppResponseError(
                "Embedding response has an unexpected vector count"
            )
        by_index: dict[int, list[float]] = {}
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("index"), int):
                raise LlamaCppResponseError("Embedding response indices are invalid")
            index = item["index"]
            vector = item.get("embedding")
            if index in by_index or not isinstance(vector, list):
                raise LlamaCppResponseError(
                    "Embedding response indices are missing or duplicate"
                )
            if len(vector) != expected_dimension:
                raise LlamaCppResponseError(
                    f"Embedding dimension mismatch: expected {expected_dimension}, got {len(vector)}"
                )
            converted = [float(value) for value in vector]
            if not all(math.isfinite(value) for value in converted):
                raise LlamaCppResponseError("Embedding vector values must be finite")
            by_index[index] = converted
        expected_indices = set(range(len(texts)))
        if set(by_index) != expected_indices:
            raise LlamaCppResponseError(
                "Embedding response indices are missing or out of range"
            )
        return [by_index[index] for index in range(len(texts))]

    def rerank_native(
        self, query: str, documents: list[str], model: str
    ) -> list[float]:
        if not documents:
            return []
        payload = self._request(
            "/v1/rerank",
            {"model": model, "query": query, "documents": list(documents)},
        )
        results = payload.get("results")
        if not isinstance(results, list) or len(results) != len(documents):
            raise LlamaCppResponseError("Rerank response has an unexpected score count")
        by_index: dict[int, float] = {}
        for item in results:
            if not isinstance(item, dict) or not isinstance(item.get("index"), int):
                raise LlamaCppResponseError("Rerank response indices are invalid")
            index = item["index"]
            if index in by_index:
                raise LlamaCppResponseError("Rerank response indices are duplicate")
            score_raw = item.get("relevance_score")
            if not isinstance(score_raw, int | float):
                raise LlamaCppResponseError(
                    "Rerank response relevance_score is invalid"
                )
            score = float(score_raw)
            if not math.isfinite(score):
                raise LlamaCppResponseError("Rerank scores must be finite")
            by_index[index] = score
        if set(by_index) != set(range(len(documents))):
            raise LlamaCppResponseError(
                "Rerank response indices are missing or out of range"
            )
        return [by_index[index] for index in range(len(documents))]

    def _request(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        last_error: LlamaCppRequestError | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self._post(url, json=payload, timeout=self.timeout)
            except Exception as exc:
                retryable = isinstance(
                    exc,
                    requests.exceptions.RequestException
                    | ConnectionError
                    | TimeoutError,
                )
                last_error = LlamaCppRequestError(
                    f"llama.cpp request failed for {path}: {exc}",
                    retryable=retryable,
                )
            else:
                status_code = int(getattr(response, "status_code", 200))
                if status_code >= 400:
                    body = str(getattr(response, "text", ""))[:2000]
                    retryable = status_code in {408, 429} or (
                        status_code >= 500 and INPUT_TOO_LARGE not in body
                    )
                    detail = f": {body}" if body else ""
                    last_error = LlamaCppRequestError(
                        f"llama.cpp request failed for {path}: HTTP {status_code}{detail}",
                        status_code=status_code,
                        retryable=retryable,
                        context_size=_context_size(body)
                        if status_code == 400
                        else None,
                    )
                else:
                    try:
                        result = response.json()
                    except Exception as exc:
                        raise LlamaCppResponseError(
                            f"llama.cpp response for {path} is not valid JSON: {exc}"
                        ) from exc
                    if not isinstance(result, dict):
                        raise LlamaCppResponseError(
                            f"llama.cpp response for {path} must be an object"
                        )
                    return result
            if (
                last_error is None
                or not last_error.retryable
                or attempt >= self.max_attempts
            ):
                break
            self._sleep(self.retry_delay_seconds * attempt)
        assert last_error is not None
        raise last_error
