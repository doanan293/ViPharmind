from json import dumps as json_text

import pytest

from pharma_lab.runtime.client import (
    LlamaCppClient,
    LlamaCppRequestError,
    LlamaCppResponseError,
)


class JsonResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self) -> object:
        return self.payload


def test_rerank_native_returns_scores_in_document_order():
    seen = []

    def post(url, json, timeout):
        seen.append((url, json))
        return JsonResponse(
            {
                "results": [
                    {"index": 1, "relevance_score": 0.2},
                    {"index": 0, "relevance_score": 0.9},
                ]
            }
        )

    client = LlamaCppClient("http://server", post=post)

    assert client.rerank_native("q", ["a", "b"], "model") == [0.9, 0.2]
    assert seen == [
        (
            "http://server/v1/rerank",
            {"model": "model", "query": "q", "documents": ["a", "b"]},
        )
    ]


def test_rerank_native_rejects_duplicate_indices():
    client = LlamaCppClient(
        "http://server",
        post=lambda *_args, **_kwargs: JsonResponse(
            {
                "results": [
                    {"index": 0, "relevance_score": 0.5},
                    {"index": 0, "relevance_score": 0.4},
                ]
            }
        ),
    )

    with pytest.raises(LlamaCppResponseError, match="duplicate"):
        client.rerank_native("q", ["a", "b"], "model")


def test_sync_request_retries_retryable_http_status():
    attempts = 0

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.text = "busy"

        def json(self):
            return {"ok": True}

    def post(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        return Response(503 if attempts == 1 else 200)

    client = LlamaCppClient(
        "http://server", post=post, max_attempts=2, retry_delay_seconds=0
    )

    assert client._request("/health", {}) == {"ok": True}
    assert attempts == 2


def test_sync_request_does_not_retry_an_input_too_large_error():
    """llama.cpp answers 500 for a prompt larger than the physical batch.

    The same input fails again on a fresh server, so a retry only wastes a server
    lifetime and, on Kaggle, a whole GPU session.
    """
    attempts = 0

    class Response:
        status_code = 500
        text = (
            '{"error":{"code":500,"message":"input (2070 tokens) is too large to '
            'process. increase the physical batch size (current batch size: 2048)",'
            '"type":"server_error"}}'
        )

        def json(self):
            return {}

    def post(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        return Response()

    client = LlamaCppClient(
        "http://server", post=post, max_attempts=3, retry_delay_seconds=0
    )

    with pytest.raises(LlamaCppRequestError, match="too large to process") as raised:
        client._request("/v1/rerank", {})
    assert raised.value.retryable is False
    assert attempts == 1


class FakeEmbeddingServer:
    """Embeds at most `n_ctx` tokens per input, as llama.cpp does.

    It tokenizes a string as one token per word, wrapped in BOS 1 and EOS 2 when
    `add_special` is set, and embeds an input as its token count.
    """

    def __init__(self, n_ctx: int) -> None:
        self.n_ctx = n_ctx
        self.embedded_inputs: list[list[object]] = []

    def tokens(self, text: str, add_special: bool) -> list[int]:
        words = [100 + len(word) for word in text.split()]
        return [1, *words, 2] if add_special else words

    def post(self, url, json, timeout):
        if url.endswith("/tokenize"):
            return JsonResponse(
                {"tokens": self.tokens(json["content"], json["add_special"])}
            )
        inputs = json["input"]
        sizes = [
            len(item) if isinstance(item, list) else len(self.tokens(item, True))
            for item in inputs
        ]
        if max(sizes) > self.n_ctx:
            response = JsonResponse({}, status_code=400)
            response.text = json_text(
                {
                    "error": {
                        "code": 400,
                        "message": "input is larger than the max context size",
                        "type": "exceed_context_size_error",
                        "n_prompt_tokens": max(sizes),
                        "n_ctx": self.n_ctx,
                    }
                }
            )
            return response
        self.embedded_inputs.append(list(inputs))
        return JsonResponse(
            {
                "data": [
                    {"index": index, "embedding": [float(size)]}
                    for index, size in enumerate(sizes)
                ]
            }
        )


def test_embed_cuts_an_input_longer_than_the_server_context():
    """A model with a short context (EmbeddingGemma: 2,048 tokens) embeds the head of a
    long chunk, as sentence-transformers truncates at max_seq_length."""
    server = FakeEmbeddingServer(n_ctx=5)
    client = LlamaCppClient("http://server", post=server.post, retry_delay_seconds=0)

    vectors = client.embed(["a bb", "a bb ccc dddd eeeee"], "model", 1)

    assert vectors == [[4.0], [5.0]]
    assert server.embedded_inputs[-1] == ["a bb", [1, 101, 102, 103, 2]]


def test_embed_sends_text_unchanged_when_it_fits():
    server = FakeEmbeddingServer(n_ctx=5)
    client = LlamaCppClient("http://server", post=server.post)

    assert client.embed(["a bb ccc"], "model", 1) == [[5.0]]
    assert server.embedded_inputs == [["a bb ccc"]]


def test_embed_does_not_retry_a_context_overflow_as_is():
    server = FakeEmbeddingServer(n_ctx=3)
    calls = []

    def post(url, json, timeout):
        calls.append(url)
        return server.post(url, json, timeout)

    client = LlamaCppClient(
        "http://server", post=post, max_attempts=3, retry_delay_seconds=0
    )

    assert client.embed(["a bb ccc"], "model", 1) == [[3.0]]
    assert calls.count("http://server/v1/embeddings") == 2
