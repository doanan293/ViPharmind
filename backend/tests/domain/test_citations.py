from pharma_agent.domain.agent.citations import (
    SNIPPET_CHARS,
    CitationSanitizer,
    citations_from,
)
from pharma_agent.domain.retrieval.evidence import EvidenceSet
from pharma_agent.domain.shared.text import make_snippet
from tests.domain.factories import RELEASE_ID, SOURCE, chunk_uuid, make_hit


def run_stream(deltas: list[str], valid: set[int]) -> tuple[str, list[int]]:
    sanitizer = CitationSanitizer(valid)
    out = "".join(sanitizer.feed(d) for d in deltas) + sanitizer.flush()
    return out, sanitizer.used


def test_marker_split_across_deltas_is_reassembled() -> None:
    out, used = run_stream(["Liều 500 mg [", "1", "] mỗi 6 giờ [2]."], {1, 2})
    assert out == "Liều 500 mg [1] mỗi 6 giờ [2]."
    assert used == [1, 2]


def test_invalid_marker_is_dropped_and_used_is_deduped() -> None:
    out, used = run_stream(["A [7] B [1] C [1]"], {1})
    assert out == "A  B [1] C [1]"
    assert used == [1]


def test_non_citation_brackets_pass_through() -> None:
    out, _ = run_stream(["x [ghi chú] y [", "abc] z"], {1})
    assert out == "x [ghi chú] y [abc] z"


def test_unfinished_marker_is_flushed_verbatim() -> None:
    sanitizer = CitationSanitizer({1})
    assert sanitizer.feed("cuối [1") == "cuối "
    assert sanitizer.flush() == "[1"


def test_citations_from_numbered_evidence() -> None:
    evidence = EvidenceSet()
    evidence.merge(
        [
            make_hit("c1", rerank=0.9),
            make_hit("c2", rerank=0.8, start_page=None, end_page=None),
        ]
    )
    packed = evidence.pack(10_000)
    _, numbered = evidence.context_view(packed)
    citations = citations_from(numbered, used=[2, 1])
    assert [c.index for c in citations] == [2, 1]
    second, first = citations
    assert (second.chunk_version_id, second.start_page, second.end_page) == (
        chunk_uuid("c2"),
        None,
        None,
    )
    assert (first.chunk_version_id, first.release_id) == (chunk_uuid("c1"), RELEASE_ID)
    assert (first.source, first.title, first.section, first.start_page) == (
        SOURCE,
        "Paracetamol",
        "Liều dùng",
        10,
    )
    assert first.snippet == make_snippet("paracetamol 500 mg", SNIPPET_CHARS)
    assert citations_from(numbered, used=[3]) == []


def test_grouped_markers_become_separate_markers() -> None:
    # Models also write "[1, 2, 4]"; the UI renders only "[n]" markers.
    text, used = run_stream(["Tối đa 4 g [1, 2, 4] mỗi ngày [3; 5]."], {1, 2, 3, 4, 5})
    assert text == "Tối đa 4 g [1], [2], [4] mỗi ngày [3], [5]."
    assert used == [1, 2, 4, 3, 5]


def test_grouped_marker_keeps_only_valid_indexes() -> None:
    text, used = run_stream(["liều [2, 9]; xem [8, 9]."], {1, 2})
    assert text == "liều [2]; xem ."
    assert used == [2]


def test_grouped_marker_split_across_deltas() -> None:
    text, used = run_stream(["giảm liều [1,", " 3] khi suy gan"], {1, 3})
    assert text == "giảm liều [1], [3] khi suy gan"
    assert used == [1, 3]


def test_citation_snippets_are_previews_without_markdown() -> None:
    # The stored citation is what the hover card shows: markdown markers must not reach it.
    evidence = EvidenceSet()
    evidence.merge(
        [make_hit("c1", rerank=0.9, text="## Liều dùng\n- **Người lớn:** 500 mg")]
    )
    _, numbered = evidence.context_view(evidence.pack(10_000))
    (citation,) = citations_from(numbered, used=[1])
    assert citation.snippet == "Liều dùng Người lớn: 500 mg"
