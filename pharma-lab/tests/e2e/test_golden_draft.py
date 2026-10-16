from pharma_agent.domain.llm.models import LlmRole
from pharma_agent.domain.llm.port import LlmError
from tests.e2e.factories import ScriptedLlm

from pharma_lab.e2e.corpus_text import CorpusText
from pharma_lab.e2e.golden import Category, ExpectedBehavior
from pharma_lab.e2e.golden_draft import (
    DraftFact,
    DraftFailure,
    DraftReference,
    allocate,
    draft_multi_hop,
    select_candidates,
    to_item,
    used_query_ids,
    write_drafts,
)

A = "drug:paracetamol:lieu-dung"
B = "drug:paracetamol:chong-chi-dinh"
CORPUS = CorpusText(
    sections={
        A: "Người lớn: 500 mg mỗi 4 đến 6 giờ, tối đa 4 g mỗi ngày.",
        B: "Không dùng cho người suy gan nặng hoặc mẫn cảm với paracetamol.",
    },
    section_documents={A: "drug:paracetamol", B: "drug:paracetamol"},
    titles={"drug:paracetamol": "Paracetamol"},
)


def candidate(query_id: str, kind: str = "three_intent") -> dict[str, object]:
    return {
        "query_id": query_id,
        "query": "Paracetamol người lớn uống bao nhiêu và ai không được dùng?",
        "kind": kind,
        "eval_group": "multi_intent",
        "expected_section_ids": [A, B],
        "missing": [B],
    }


def good() -> DraftReference:
    return DraftReference(
        answer="Người lớn uống 500 mg mỗi 4 đến 6 giờ, tối đa 4 g mỗi ngày; không dùng khi suy gan nặng.",
        key_facts=[
            DraftFact(
                fact="Tối đa 4 g mỗi ngày",
                evidence_quote="tối đa 4 g mỗi ngày",
                section_id=A,
            ),
            DraftFact(
                fact="Chống chỉ định khi suy gan nặng",
                evidence_quote="người suy gan nặng",
                section_id=B,
            ),
        ],
    )


def only_first_section() -> DraftReference:
    return DraftReference(answer="Tối đa 4 g mỗi ngày.", key_facts=good().key_facts[:1])


def test_allocate_spreads_the_total_and_caps_each_kind() -> None:
    assert allocate({"a": 100, "b": 100, "c": 100, "d": 100}, 150, 45) == {
        "a": 38,
        "b": 38,
        "c": 37,
        "d": 37,
    }
    # A short kind gives its share to the others, up to the cap.
    assert allocate({"a": 10, "b": 100, "c": 100, "d": 100}, 150, 45) == {
        "a": 10,
        "b": 45,
        "c": 45,
        "d": 45,
    }


def test_select_drops_used_queries_and_is_seeded() -> None:
    rows = [candidate(f"q{n}") for n in range(10)] + [candidate("used")]
    first = select_candidates(rows, exclude={"used"}, seed=1)
    assert first == select_candidates(rows, exclude={"used"}, seed=1)
    assert first != select_candidates(rows, exclude={"used"}, seed=2)
    assert "used" not in {r["query_id"] for r in first["three_intent"]}
    assert len(first["three_intent"]) == 10


async def test_a_valid_draft_becomes_a_multi_hop_item() -> None:
    llm = ScriptedLlm()
    llm.script(LlmRole.ANSWER, good())
    items, failures = await draft_multi_hop(
        llm, {"three_intent": [candidate("q1")]}, {"three_intent": 1}, CORPUS
    )
    assert failures == []
    (item,) = items
    assert item.item_id == "e2e-mhop-0001"
    assert item.category is Category.MULTI_HOP
    assert item.expected_behavior is ExpectedBehavior.GROUNDED
    assert item.source_query_id == "q1"
    assert item.gold_section_ids == [A, B]
    assert item.tags == ["three_intent"]
    assert item.eval_group is None
    assert [t.role for t in item.turns] == ["user"]
    prompt = llm.calls[0][1][-1].content
    assert A in prompt and "tối đa 4 g mỗi ngày" in prompt


async def test_a_draft_missing_a_gold_section_is_retried_with_the_problems() -> None:
    llm = ScriptedLlm()
    llm.script(LlmRole.ANSWER, only_first_section(), good())
    items, failures = await draft_multi_hop(
        llm, {"three_intent": [candidate("q1")]}, {"three_intent": 1}, CORPUS
    )
    assert len(items) == 1 and failures == []
    retry = llm.calls[1][1][-1].content
    assert B in retry and "no key fact" in retry


async def test_a_failing_candidate_is_replaced_by_the_next_one() -> None:
    bad_quote = DraftReference(
        answer="x",
        key_facts=[
            DraftFact(fact="x", evidence_quote="không có trong mục", section_id=A),
            DraftFact(fact="y", evidence_quote="người suy gan nặng", section_id=B),
        ],
    )
    llm = ScriptedLlm()
    llm.script(LlmRole.ANSWER, bad_quote, bad_quote, LlmError("down"), good())
    rows = [candidate("q1"), candidate("q2"), candidate("q3")]
    items, failures = await draft_multi_hop(
        llm, {"three_intent": rows}, {"three_intent": 1}, CORPUS, concurrency=1
    )
    assert [i.source_query_id for i in items] == ["q3"]
    assert [f.query_id for f in failures] == ["q1", "q2"]
    assert "quote is not in section" in failures[0].problems[0]
    assert "LlmError" in failures[1].problems[0]


async def test_ids_run_across_kinds_in_kind_order() -> None:
    llm = ScriptedLlm()
    llm.script(LlmRole.ANSWER, good(), good())
    items, _ = await draft_multi_hop(
        llm,
        {"two_drug": [candidate("q2", "two_drug")], "three_intent": [candidate("q1")]},
        {"three_intent": 1, "two_drug": 1},
        CORPUS,
    )
    assert [(i.item_id, i.tags) for i in items] == [
        ("e2e-mhop-0001", ["three_intent"]),
        ("e2e-mhop-0002", ["two_drug"]),
    ]


def test_used_queries_and_draft_batches(tmp_path) -> None:
    (tmp_path / "answerable-01.authored.jsonl").write_text(
        '{"item_id": "e2e-ans-0001", "source_query_id": "q7"}\n'
        '{"item_id": "e2e-oos-0001", "source_query_id": null}\n',
        encoding="utf-8",
    )
    (tmp_path / "answerable-01.todo.jsonl").write_text(
        '{"slot_id": "x", "source_query_id": "q8"}\n', encoding="utf-8"
    )
    assert used_query_ids(tmp_path) == {"q7"}

    item = to_item(candidate("q1"), good(), "e2e-mhop-0001")
    paths = write_drafts(
        tmp_path,
        [item] * 3,
        [DraftFailure(query_id="q2", kind="two_drug", problems=["x"])],
        batch_size=2,
    )
    assert [p.name for p in paths] == [
        "multi-hop-01.draft.jsonl",
        "multi-hop-02.draft.jsonl",
        "multi-hop.failed.jsonl",
    ]
    assert len(paths[0].read_text("utf-8").splitlines()) == 2
