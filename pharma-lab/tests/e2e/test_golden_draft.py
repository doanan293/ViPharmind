from pharma_agent.domain.llm.models import LlmRole
from pharma_agent.domain.llm.port import LlmError
from tests.e2e.factories import ScriptedLlm

from pharma_lab.e2e.corpus_text import CorpusText
from pharma_lab.e2e.golden import Category, ExpectedBehavior
from pharma_lab.e2e.golden_draft import (
    PROBE,
    DraftFact,
    DraftFailure,
    DraftReference,
    authored_documents,
    authored_sections,
    authored_state,
    draft_multi_hop,
    load_candidates,
    needed_counts,
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


def test_needed_counts_top_the_quotas_up() -> None:
    assert needed_counts({}) == {
        "retrieval_miss": 32,
        "noisy_retry": 30,
        "three_intent": 16,
        "two_drug": 42,
        "brand_to_ingredient": 30,
    }
    topped = needed_counts({"noisy_retry": 30, "three_intent": 20, "two_drug": 1})
    assert (topped["noisy_retry"], topped["three_intent"], topped["two_drug"]) == (
        0,
        0,
        41,
    )


def test_select_drops_used_queries_and_is_seeded() -> None:
    # Distinct section sets, so dedupe keeps every one.
    rows = [
        dict(candidate(f"q{n}"), expected_section_ids=[A, f"drug:x{n}:lieu-dung"])
        for n in range(10)
    ] + [candidate("used")]
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
        first_number=53,
    )
    assert [(i.item_id, i.tags) for i in items] == [
        ("e2e-mhop-0053", ["three_intent"]),
        ("e2e-mhop-0054", ["two_drug"]),
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
    # A drafted candidate is used too, whether or not the review kept it.
    (tmp_path / "multi-hop-01.draft.jsonl").write_text(
        '{"item_id": "e2e-mhop-0002", "source_query_id": "q9", "tags": ["two_drug"]}\n',
        encoding="utf-8",
    )
    (tmp_path / "multi-hop-01.authored.jsonl").write_text(
        '{"item_id": "e2e-mhop-0001", "source_query_id": "q6", "tags": ["two_drug"]}\n',
        encoding="utf-8",
    )
    assert used_query_ids(tmp_path) == {"q6", "q7", "q9"}
    assert authored_state(tmp_path) == ({"two_drug": 1}, 2)
    assert authored_documents(tmp_path, "two_drug") == []
    (tmp_path / "multi-hop-02.authored.jsonl").write_text(
        '{"item_id": "e2e-mhop-0003", "tags": ["three_intent"], '
        '"gold_section_ids": ["drug:a:x", "leaflet:t:b:01-y"]}\n',
        encoding="utf-8",
    )
    assert authored_documents(tmp_path, "three_intent") == ["drug:a", "leaflet:t:b"]
    assert authored_sections(tmp_path) == [frozenset({"drug:a:x", "leaflet:t:b:01-y"})]

    item = to_item(candidate("q1"), good(), "e2e-mhop-0003")
    paths = write_drafts(
        tmp_path,
        [item] * 3,
        [DraftFailure(query_id="q2", kind="two_drug", problems=["x"])],
        batch_size=2,
    )
    # New batches are numbered after the existing draft.
    assert [p.name for p in paths] == [
        "multi-hop-02.draft.jsonl",
        "multi-hop-03.draft.jsonl",
        "multi-hop.failed.jsonl",
    ]
    assert len(paths[0].read_text("utf-8").splitlines()) == 2


def test_load_candidates_reads_both_candidate_files(tmp_path) -> None:
    assert load_candidates(tmp_path) == []
    (tmp_path / "multi-hop.todo.jsonl").write_text(
        '{"query_id": "q1"}\n\n', encoding="utf-8"
    )
    (tmp_path / "multi-hop.generated.jsonl").write_text(
        '{"query_id": "gen-1"}\n', encoding="utf-8"
    )
    assert [r["query_id"] for r in load_candidates(tmp_path)] == ["q1", "gen-1"]


def generated(query_id: str = "gen-two-drug-0001") -> dict[str, object]:
    return dict(
        candidate(query_id, "two_drug"),
        query="Tôi đang dùng Paracetamol, thêm Ibuprofen được không?",
        generated=True,
        subjects=["Paracetamol", "Ibuprofen"],
    )


async def test_a_generated_candidate_gets_its_question_rewritten() -> None:
    dropped_a_name = DraftReference(
        answer=good().answer,
        key_facts=good().key_facts,
        question="Uống thêm Ibuprofen được không?",
    )
    rewritten = DraftReference(
        answer=good().answer,
        key_facts=good().key_facts,
        question="Đang uống Paracetamol thì thêm Ibuprofen được không?",
    )
    llm = ScriptedLlm()
    llm.script(LlmRole.ANSWER, dropped_a_name, rewritten)
    items, failures = await draft_multi_hop(
        llm, {"two_drug": [generated()]}, {"two_drug": 1}, CORPUS
    )
    assert failures == []
    assert items[0].question == rewritten.question
    first = llm.calls[0][1][-1].content
    assert "viết lại" in first and "Paracetamol, Ibuprofen" in first
    assert "no longer names Paracetamol" in llm.calls[1][1][-1].content


async def test_a_benchmark_candidate_keeps_its_question() -> None:
    llm = ScriptedLlm()
    llm.script(LlmRole.ANSWER, good().model_copy(update={"question": "Khác?"}))
    items, _ = await draft_multi_hop(
        llm, {"three_intent": [candidate("q1")]}, {"three_intent": 1}, CORPUS
    )
    assert items[0].question == candidate("q1")["query"]
    assert "viết lại" not in llm.calls[0][1][-1].content


def test_select_keeps_one_candidate_per_gold_section_set() -> None:
    reversed_sections = dict(candidate("q2"), expected_section_ids=[B, A])
    other = dict(candidate("q3"), expected_section_ids=[A])
    chosen = select_candidates(
        [candidate("q1"), reversed_sections, other], exclude=set(), seed=0
    )
    assert sorted(str(r["query_id"]) for r in chosen["three_intent"]) == ["q1", "q3"]
    # An authored item's section set keeps a renumbered generated candidate out.
    chosen = select_candidates(
        [candidate("q1"), other],
        exclude=set(),
        seed=0,
        exclude_sections=[frozenset({A, B})],
    )
    assert [str(r["query_id"]) for r in chosen["three_intent"]] == ["q3"]


async def test_a_probe_is_drafted_as_an_answerable_item_with_its_own_ids(
    tmp_path,
) -> None:
    llm = ScriptedLlm()
    llm.script(LlmRole.ANSWER, good())
    row = dict(candidate("q1", "rerank_probe"), eval_group="formulary")
    items, _ = await draft_multi_hop(
        llm, {"rerank_probe": [row]}, {"rerank_probe": 1}, CORPUS, family=PROBE
    )
    (item,) = items
    assert (item.item_id, item.category, item.tags) == (
        "e2e-ans-p0001",
        Category.ANSWERABLE,
        ["rerank_probe"],
    )
    assert item.eval_group is None
    paths = write_drafts(tmp_path, items, [], family=PROBE)
    assert [p.name for p in paths] == ["probe-01.draft.jsonl", "probe.failed.jsonl"]
    assert needed_counts({"rerank_probe": 5}, PROBE)["rerank_probe"] == 16
    (tmp_path / "probe-01.authored.jsonl").write_text(
        paths[0].read_text("utf-8"), encoding="utf-8"
    )
    assert authored_state(tmp_path, PROBE) == ({"rerank_probe": 1}, 1)
    assert authored_state(tmp_path) == ({}, 0)
