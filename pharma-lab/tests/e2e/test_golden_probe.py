import pytest

from pharma_lab.e2e.corpus_text import CorpusText
from pharma_lab.e2e.golden_probe import ProbeRuns, probe_candidates, probe_kind

LONG = " ".join(["liều"] * 30)
CORPUS = CorpusText(
    sections={"drug:a:lieu": LONG, "drug:a:than-trong": "ngắn", "drug:b:lieu": LONG},
    section_documents={},
    titles={},
)


def row(query_id: str, sections: list[str], query: str = "Liều a?") -> dict:
    return {
        "query_id": query_id,
        "query": query,
        "eval_group": "formulary",
        "answer_mode": "single",
        "expected_section_id": sections[0],
        "expected_section_ids": sections,
    }


def runs(**cover: tuple[bool, bool, bool, bool]) -> ProbeRuns:
    rows = {q: row(q, ["drug:a:lieu"]) for q in cover}
    return ProbeRuns(
        rows,
        {q: c[0] for q, c in cover.items()},
        {q: c[1] for q, c in cover.items()},
        {q: c[2] for q, c in cover.items()},
        {q: c[3] for q, c in cover.items()},
    )


@pytest.mark.parametrize(
    ("full", "no_rerank", "bm25", "dense", "kind"),
    [
        (True, False, True, True, "rerank_probe"),
        (True, True, True, False, "lexical_probe"),
        (True, True, False, True, "semantic_probe"),
        # Reranking is the rarer component and wins when both apply.
        (True, False, False, True, "rerank_probe"),
        (True, True, True, True, None),
        (False, False, False, False, None),
    ],
)
def test_probe_kind_names_the_component_that_decides_coverage(
    full: bool, no_rerank: bool, bm25: bool, dense: bool, kind: str | None
) -> None:
    assert probe_kind("q", runs(q=(full, no_rerank, bm25, dense))) == kind


def test_probe_candidates_keep_informative_single_section_questions() -> None:
    probe = runs(q1=(True, False, True, True), q2=(True, False, True, True))
    probe.rows["q2"] = row("q2", ["drug:a:than-trong"])
    probe.rows["q3"] = row("q3", ["drug:a:lieu", "drug:b:lieu"])
    probe.full["q3"], probe.no_rerank["q3"] = True, False
    probe.bm25_depth["q3"], probe.dense_depth["q3"] = True, True
    rows = probe_candidates(probe, CORPUS)
    # q2's section is too short to answer from; q3 needs two sections.
    assert [(r["query_id"], r["kind"], r["expected_section_ids"]) for r in rows] == [
        ("q1", "rerank_probe", ["drug:a:lieu"])
    ]
