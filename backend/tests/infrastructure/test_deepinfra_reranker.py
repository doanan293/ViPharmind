import json

import httpx
import pytest
import respx

from pharma_agent.domain.retrieval.ports import RetrievalError
from pharma_agent.infrastructure.retrieval.deepinfra_reranker import DeepInfraReranker
from pharma_agent.infrastructure.retrieval.rerankers import build_reranker
from pharma_agent.infrastructure.settings import RerankSettings
from tests.domain.factories import chunk_uuid, make_hit

BASE = "https://api.deepinfra.com"
MODEL = "Qwen/Qwen3-Reranker-4B"
URL = f"/v1/inference/{MODEL}"


@respx.mock(base_url=BASE)
async def test_scores_pair_each_query_with_its_document(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.post(URL).mock(
        return_value=httpx.Response(200, json={"scores": [0.1, 0.9], "input_tokens": 9})
    )
    async with httpx.AsyncClient(base_url=BASE) as http:
        hits = await DeepInfraReranker(http, model=MODEL).rerank(
            "Q", [make_hit("a"), make_hit("b")], top_n=2
        )
    assert [h.chunk_version_id for h in hits] == [chunk_uuid("b"), chunk_uuid("a")]
    assert hits[0].rerank_score == 0.9
    body = json.loads(route.calls[0].request.content)
    assert body["queries"] == ["Q", "Q"] and len(body["documents"]) == 2


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"scores": [0.1]}),
        httpx.Response(200, json={"nothing": []}),
        httpx.Response(500, json={}),
    ],
)
async def test_bad_answers_are_retrieval_errors(response: httpx.Response) -> None:
    with respx.mock(base_url=BASE) as router:
        router.post(URL).mock(return_value=response)
        async with httpx.AsyncClient(base_url=BASE) as http:
            with pytest.raises(RetrievalError):
                await DeepInfraReranker(http, model=MODEL).rerank(
                    "Q", [make_hit("a"), make_hit("b")], top_n=2
                )


async def test_no_hits_make_no_request() -> None:
    async with httpx.AsyncClient(base_url=BASE) as http:
        assert await DeepInfraReranker(http, model=MODEL).rerank("Q", [], 3) == []


def test_the_protocol_setting_selects_deepinfra() -> None:
    reranker = build_reranker(
        RerankSettings(protocol="deepinfra", base_url=BASE, api_key="k", model=MODEL)
    )
    assert isinstance(reranker, DeepInfraReranker)
