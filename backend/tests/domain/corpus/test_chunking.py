import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pydantic import TypeAdapter

from pharma_agent.domain.corpus import bundle, chunking, enrichment, identity
from pharma_agent.domain.corpus.bundle import (
    BlockKind,
    BlockRecord,
    ColloquialMappingRecord,
    DocumentRecord,
    GlossaryEntry,
    SectionRecord,
)
from pharma_agent.domain.corpus.chunking import (
    CHUNKER_VERSION,
    MAX_CHUNK_CHARS,
    TARGET_CHUNK_CHARS,
    chunk_document,
)
from pharma_agent.domain.corpus.identity import chunk_version_id, sha256_hex

GOLDEN: dict[str, Any] = json.loads(
    (Path(__file__).parent / "golden" / "chunking_v2.json").read_text(encoding="utf-8")
)
CASES: list[dict[str, Any]] = GOLDEN["cases"]
GLOSSARY = TypeAdapter(list[GlossaryEntry]).validate_json(
    json.dumps(GOLDEN["glossary"])
)
MAPPINGS = TypeAdapter(list[ColloquialMappingRecord]).validate_json(
    json.dumps(GOLDEN["colloquial_mappings"])
)
PUBLIC_API: dict[ModuleType, list[str]] = {
    bundle: [
        "BUNDLE_SCHEMA_VERSION",
        "KnowledgeBundle",
        "BundleValidationError",
        "read_bundle",
        "write_bundle",
        "model_slug",
        "encode_vector",
        "decode_vector",
    ],
    identity: ["CORPUS_NAMESPACE", "canonical_json", "sha256_hex", "chunk_version_id"],
    chunking: [
        "CHUNKER_VERSION",
        "TARGET_CHUNK_CHARS",
        "MAX_CHUNK_CHARS",
        "ChunkDraft",
        "chunk_document",
        "section_text",
    ],
    enrichment: [
        "build_context_header",
        "detect_terms",
        "mapping_for_section",
        "compose_embedding_text",
    ],
}


def load_case(name: str) -> tuple[DocumentRecord, list[SectionRecord], int, int]:
    case = next(case for case in CASES if case["name"] == name)
    return (
        DocumentRecord.model_validate_json(json.dumps(case["document"])),
        TypeAdapter(list[SectionRecord]).validate_json(json.dumps(case["sections"])),
        case["target_chars"],
        case["max_chars"],
    )


def _section(key: str, heading: str, text: str, ordinal: int) -> SectionRecord:
    return SectionRecord(
        key=key,
        document_key="drug:paracetamol",
        heading=heading,
        context_path=[heading],
        ordinal=ordinal,
        blocks=[BlockRecord(kind=BlockKind.PROSE, markdown=text)],
    )


def _document() -> DocumentRecord:
    return DocumentRecord.model_validate_json(
        json.dumps(
            {
                "key": "drug:paracetamol",
                "kind": "drug_monograph",
                "title": "Paracetamol",
                "source": {"title": "Dược thư", "url": None},
            }
        )
    )


def test_short_sections_pack_into_one_chunk_in_document_order() -> None:
    sections = [
        _section("drug:paracetamol:lieu-dung", "Liều dùng", "500 mg.", 2),
        _section("drug:paracetamol:chi-dinh", "Chỉ định", "Giảm đau.", 1),
    ]

    (chunk,) = chunk_document(_document(), sections, [], [])

    assert chunk.section_keys == [
        "drug:paracetamol:chi-dinh",
        "drug:paracetamol:lieu-dung",
    ]
    assert chunk.headings == ["Chỉ định", "Liều dùng"]
    assert chunk.chunk_text == "## Chỉ định\n\nGiảm đau.\n\n## Liều dùng\n\n500 mg."
    assert chunk.context_header == "Paracetamol > Chỉ định; Liều dùng"
    assert chunk.ordinal == 1 and chunk.document_key == "drug:paracetamol"


def test_a_new_chunk_starts_when_the_target_would_be_exceeded() -> None:
    body = "x" * (TARGET_CHUNK_CHARS // 2)
    sections = [
        _section(f"drug:paracetamol:s{i}", f"Mục {i}", body, i) for i in range(1, 4)
    ]

    chunks = chunk_document(_document(), sections, [], [])

    assert [c.section_keys for c in chunks] == [
        ["drug:paracetamol:s1"],
        ["drug:paracetamol:s2"],
        ["drug:paracetamol:s3"],
    ]
    assert [c.ordinal for c in chunks] == [1, 2, 3]


def test_oversized_section_splits_alone() -> None:
    long = "\n\n".join(f"Đoạn {i} " + "y" * 900 for i in range(10))
    sections = [
        _section("drug:paracetamol:s1", "Mục 1", "ngắn", 1),
        _section("drug:paracetamol:s2", "Mục 2", long, 2),
        _section("drug:paracetamol:s3", "Mục 3", "ngắn", 3),
    ]

    chunks = chunk_document(_document(), sections, [], [])

    assert chunks[0].section_keys == ["drug:paracetamol:s1"]
    middle = [c for c in chunks if c.section_keys == ["drug:paracetamol:s2"]]
    assert len(middle) >= 2
    assert all(len(c.chunk_text) <= MAX_CHUNK_CHARS for c in middle)
    assert all(c.chunk_text.startswith("## Mục 2\n\n") for c in middle)
    assert chunks[-1].section_keys == ["drug:paracetamol:s3"]
    assert [c.ordinal for c in chunks] == list(range(1, len(chunks) + 1))


def test_blank_section_yields_nothing() -> None:
    sections = [
        _section("drug:paracetamol:s1", "Mục 1", "   ", 1),
        _section("drug:paracetamol:s2", "Mục 2", "có chữ", 2),
    ]

    (chunk,) = chunk_document(_document(), sections, [], [])

    assert chunk.section_keys == ["drug:paracetamol:s2"]
    assert "Mục 1" not in chunk.chunk_text
    assert chunk_document(_document(), sections[:1], [], []) == []


def test_pages_span_the_packed_sections() -> None:
    first = _section("drug:paracetamol:s1", "Mục 1", "a", 1).model_copy(
        update={"start_page": 10, "end_page": 10}
    )
    second = _section("drug:paracetamol:s2", "Mục 2", "b", 2).model_copy(
        update={"start_page": 11, "end_page": 12}
    )

    (chunk,) = chunk_document(_document(), [first, second], [], [])

    assert (chunk.start_page, chunk.end_page) == (10, 12)


def test_context_header_falls_back_to_the_title_or_the_headings() -> None:
    section = _section("drug:paracetamol:s1", "Liều dùng", "a", 1)
    untitled = _document().model_copy(update={"title": ""})
    no_heading = section.model_copy(update={"heading": ""})

    assert chunk_document(untitled, [section], [], [])[0].context_header == "Liều dùng"
    assert chunk_document(_document(), [no_heading], [], [])[0].context_header == (
        "Paracetamol"
    )
    assert chunk_document(_document(), [no_heading], [], [])[0].chunk_text == "a"


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_chunk_document_matches_the_golden_output(case: dict[str, Any]) -> None:
    document, sections, target_chars, max_chars = load_case(case["name"])

    drafts = chunk_document(
        document,
        sections,
        GLOSSARY,
        MAPPINGS,
        target_chars=target_chars,
        max_chars=max_chars,
    )

    assert [
        {
            "ordinal": draft.ordinal,
            "section_keys": draft.section_keys,
            "headings": draft.headings,
            "chunk_text": draft.chunk_text,
            "start_page": draft.start_page,
            "end_page": draft.end_page,
            "context_header": draft.context_header,
            "embedding_text": draft.embedding_text,
            "term_annotations": [a.model_dump() for a in draft.term_annotations],
            "colloquial": draft.colloquial.model_dump(exclude_defaults=True)
            if draft.colloquial is not None
            else None,
        }
        for draft in drafts
    ] == case["expected"]


def test_chunk_drafts_carry_their_identities() -> None:
    for case in CASES:
        document, sections, target_chars, max_chars = load_case(case["name"])
        for draft in chunk_document(
            document,
            sections,
            GLOSSARY,
            MAPPINGS,
            target_chars=target_chars,
            max_chars=max_chars,
        ):
            assert draft.document_key == document.key
            assert draft.embedding_text_sha256 == sha256_hex(draft.embedding_text)
            assert draft.chunk_version_id == chunk_version_id(
                document.key, draft.chunk_text, draft.embedding_text, CHUNKER_VERSION
            )


def test_chunk_document_is_deterministic() -> None:
    document, sections, target_chars, max_chars = load_case("monograph")

    first = chunk_document(
        document,
        sections,
        GLOSSARY,
        MAPPINGS,
        target_chars=target_chars,
        max_chars=max_chars,
    )
    second = chunk_document(
        document.model_copy(deep=True),
        [s.model_copy(deep=True) for s in sections],
        list(GLOSSARY),
        list(MAPPINGS),
        target_chars=target_chars,
        max_chars=max_chars,
    )

    assert first == second
    assert len({draft.chunk_version_id for draft in first}) == len(first) >= 2


def test_glossary_change_creates_new_versions_only_for_affected_chunks() -> None:
    document, sections, target_chars, max_chars = load_case("monograph")
    without_adr = [entry for entry in GLOSSARY if entry.term != "ADR"]

    before = chunk_document(
        document,
        sections,
        GLOSSARY,
        MAPPINGS,
        target_chars=target_chars,
        max_chars=max_chars,
    )
    after = chunk_document(
        document,
        sections,
        without_adr,
        MAPPINGS,
        target_chars=target_chars,
        max_chars=max_chars,
    )

    assert [d.chunk_text for d in after] == [d.chunk_text for d in before]
    changed = [
        old.ordinal
        for old, new in zip(before, after, strict=True)
        if old.chunk_version_id != new.chunk_version_id
    ]
    assert changed == [old.ordinal for old in before if "ADR" in old.chunk_text]
    assert changed


def test_colloquial_mapping_change_creates_new_versions() -> None:
    document, sections, target_chars, max_chars = load_case("leaflet")
    edited = [MAPPINGS[0].model_copy(update={"visual_sign": "Vỉ thuốc màu đỏ"})]

    before = chunk_document(
        document,
        sections,
        GLOSSARY,
        MAPPINGS,
        target_chars=target_chars,
        max_chars=max_chars,
    )
    after = chunk_document(
        document,
        sections,
        GLOSSARY,
        edited,
        target_chars=target_chars,
        max_chars=max_chars,
    )

    assert before and all(
        old.chunk_version_id != new.chunk_version_id
        for old, new in zip(before, after, strict=True)
    )


def test_chunker_version_change_creates_new_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, sections, target_chars, max_chars = load_case("list")

    before = chunk_document(
        document,
        sections,
        GLOSSARY,
        MAPPINGS,
        target_chars=target_chars,
        max_chars=max_chars,
    )
    monkeypatch.setattr(chunking, "CHUNKER_VERSION", "chunker-test")
    after = chunk_document(
        document,
        sections,
        GLOSSARY,
        MAPPINGS,
        target_chars=target_chars,
        max_chars=max_chars,
    )

    assert CHUNKER_VERSION == "chunker-v2"
    assert [d.chunk_text for d in after] == [d.chunk_text for d in before]
    assert not {d.chunk_version_id for d in before} & {
        d.chunk_version_id for d in after
    }


@pytest.mark.parametrize(
    "module", list(PUBLIC_API), ids=[module.__name__ for module in PUBLIC_API]
)
def test_public_api_for_pharma_lab_is_documented(module: ModuleType) -> None:
    assert "Public API" in (module.__doc__ or "")
    for name in PUBLIC_API[module]:
        assert hasattr(module, name), f"{module.__name__}.{name}"
