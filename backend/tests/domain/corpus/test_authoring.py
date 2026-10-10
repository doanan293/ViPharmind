import uuid
from datetime import UTC, datetime

from pharma_agent.domain.corpus.authoring import (
    build_bundle,
    section_choices,
    section_key,
    slugify,
    split_markdown,
)
from pharma_agent.domain.corpus.bundle import (
    BlockKind,
    ColloquialMappingRecord,
    DocumentKind,
    GlossaryEntry,
)
from pharma_agent.domain.corpus.models import (
    Collection,
    Visibility,
    build_snapshot,
    bundle_digest,
    collection_id_for,
)
from pharma_agent.domain.corpus.source import SourceDocument

NOW = datetime(2026, 10, 11, tzinfo=UTC)
COLLECTION = Collection(
    id=collection_id_for("u-1a2b3c4d"),
    key="u-1a2b3c4d",
    title="Ghi chú",
    owner_user_id=uuid.uuid4(),
    visibility=Visibility.PRIVATE,
)
MARKDOWN = (
    "Giới thiệu.\n\n"
    "# Liều dùng\n\n"
    "Người lớn 500 mg.\n\n"
    "| Tuổi | Liều |\n|---|---|\n| <6 | 120 mg |\n\n"
    "## Trẻ em\n\n"
    "Theo cân nặng.\n\n"
    "```\n# not a heading\n```\n"
)


def document(markdown: str = MARKDOWN, key: str = "paracetamol") -> SourceDocument:
    return SourceDocument(
        id=uuid.uuid4(),
        collection_id=COLLECTION.id,
        key=key,
        title="Paracetamol",
        kind=DocumentKind.DRUG_MONOGRAPH,
        source_title="Dược thư",
        source_url=None,
        markdown=markdown,
        char_count=len(markdown),
        created_by=None,
        created_at=NOW,
        updated_by=None,
        updated_at=NOW,
    )


def test_headings_split_sections_and_tables_become_blocks() -> None:
    sections = split_markdown(MARKDOWN, fallback_heading="Paracetamol")
    assert [s.heading for s in sections] == ["Paracetamol", "Liều dùng", "Trẻ em"]
    assert [s.path for s in sections] == [(), ("Liều dùng",), ("Liều dùng", "Trẻ em")]
    dose = sections[1]
    assert [b.kind for b in dose.blocks] == [BlockKind.PROSE, BlockKind.TABLE]
    assert dose.blocks[1].table_key == "t1"
    assert dose.blocks[1].markdown.startswith("| Tuổi")
    assert sections[2].blocks[0].markdown == (
        "Theo cân nặng.\n\n```\n# not a heading\n```"
    )


def test_a_table_only_document_still_yields_one_section() -> None:
    sections = split_markdown(
        "| a | b |\n|---|---|\n| 1 | 2 |", fallback_heading="Bảng"
    )
    assert len(sections) == 1
    assert [b.kind for b in sections[0].blocks] == [BlockKind.TABLE]


def test_empty_heading_sections_are_dropped() -> None:
    sections = split_markdown("# A\n\n# B\n\nText", fallback_heading="Doc")
    assert [s.heading for s in sections] == ["B"]


def test_keys_are_stable_ascii_and_namespaced() -> None:
    assert slugify("Liều dùng cho Trẻ em!") == "lieu-dung-cho-tre-em"
    assert slugify("Đường uống") == "duong-uong"
    assert section_key("u-1a2b3c4d:paracetamol", ("Liều dùng", "Trẻ em")) == (
        "u-1a2b3c4d:paracetamol#lieu-dung/tre-em"
    )
    assert section_key("d", ()) == "d#body"


def test_build_bundle_is_stable_and_imports() -> None:
    glossary = [GlossaryEntry(term="ADR", vietnamese_expansions=["phản ứng có hại"])]
    keys = [key for key, _ in section_choices(COLLECTION, [document()])]
    mapping = ColloquialMappingRecord(
        key="hạ sốt", aliases=["thuốc hạ sốt"], section_keys=[keys[1], "gone#x"]
    )
    bundle = build_bundle(COLLECTION, [document()], glossary, [mapping])
    again = build_bundle(COLLECTION, [document()], glossary, [mapping])
    assert bundle_digest(bundle) == bundle_digest(again)
    assert bundle.manifest.collection.key == COLLECTION.key
    assert bundle.manifest.document_count == 1
    assert bundle.manifest.section_count == len(bundle.sections) == 3
    assert [d.key for d in bundle.documents] == ["u-1a2b3c4d:paracetamol"]
    assert bundle.colloquial_mappings[0].section_keys == [keys[1]]
    snapshot = build_snapshot(bundle)
    assert snapshot.chunks and snapshot.collection.id == COLLECTION.id


def test_section_choices_label_document_and_heading() -> None:
    choices = section_choices(COLLECTION, [document()])
    assert choices[1] == (
        "u-1a2b3c4d:paracetamol#lieu-dung",
        "Paracetamol › Liều dùng",
    )
