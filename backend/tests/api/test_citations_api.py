from pharma_agent.domain.conversation.models import CitationBlock
from tests.api.harness import OWNER, build_harness
from tests.citations import build_citation, chunk_id

MESSAGE_ID = "d" * 32


async def test_citation_detail_endpoint() -> None:
    harness = build_harness()
    harness.citations.blocks[(OWNER.hex, MESSAGE_ID, 1)] = CitationBlock(
        citation=build_citation(1, chunk=1),
        text="## Liều dùng\n\n| Tuổi | Liều |\n| --- | --- |\n| 1 | x |",
        is_current=True,
    )

    async with harness.client() as client:
        found = await client.get(f"/api/v1/messages/{MESSAGE_ID}/citations/1")
        missing = await client.get(f"/api/v1/messages/{MESSAGE_ID}/citations/2")
        zero = await client.get(f"/api/v1/messages/{MESSAGE_ID}/citations/0")
        bad_id = await client.get("/api/v1/messages/nope/citations/1")

    assert found.status_code == 200, found.text
    body = found.json()
    assert (body["is_current"], body["document_title"], body["section"]) == (
        True,
        "Paracetamol",
        "Liều lượng và cách dùng",
    )
    assert body["text"] == "## Liều dùng\n\n| Tuổi | Liều |\n| --- | --- |\n| 1 | x |"
    assert "chunks" not in body and "strategy" not in body
    assert body["start_page"] == 812 and str(chunk_id(1))
    assert missing.status_code == 404
    assert missing.headers["content-type"] == "application/problem+json"
    assert missing.json()["code"] == "CITATION_NOT_FOUND"
    assert missing.json()["type"] == "urn:pharma-agent:problem:citation-not-found"
    assert zero.status_code == 422 and zero.json()["code"] == "VALIDATION_ERROR"
    assert bad_id.status_code == 422
