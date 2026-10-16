import json
import shutil
from pathlib import Path

import pytest
from pharma_agent.domain.corpus.bundle import (
    BUNDLE_SCHEMA_VERSION,
    BlockKind,
    BundleChunking,
    BundleCollection,
    ColloquialMappingRecord,
    DocumentKind,
    KnowledgeBundle,
    SourceInfo,
    read_bundle,
)

from pharma_lab.bundle.chunks import gold_chunk_label, iter_document_chunks
from pharma_lab.bundle.export import (
    COLLECTION_KEY,
    COLLECTION_TITLE,
    ExportRequest,
    ExportResult,
    block_kind_for,
    document_for_section,
    export_bundle,
    is_cross_reference_only,
    leaflet_blocks,
    leaflet_body,
)
from pharma_lab.corpus.canonical.build_canonical_rag import (
    ATC_SECTION_ID,
    BRAND_INDEX_SECTION_ID,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "rag_final_small"
DOSAGE = "drug:paracetamol:lieu-luong-va-cach-dung"
PANADOL = "leaflet:thuoc:panadol-extra-gsk-150-vien-11440"
HAPACOL = "leaflet:thuoc:hapacol-250-dhg-11500"


def _request(output_dir: Path, *, force: bool = False) -> ExportRequest:
    return ExportRequest(
        rag_final_dir=FIXTURE,
        glossary_path=FIXTURE / "term_glossary.json",
        mappings_path=FIXTURE / "colloquial_mappings.json",
        output_dir=output_dir,
        force=force,
    )


def _export(tmp_path: Path) -> tuple[ExportResult, KnowledgeBundle]:
    result = export_bundle(_request(tmp_path / "bundle"))
    return result, read_bundle(tmp_path / "bundle")


def test_export_groups_documents_and_keeps_section_keys(tmp_path: Path) -> None:
    result, bundle = _export(tmp_path)

    assert [document.key for document in bundle.documents] == [
        "drug:paracetamol",
        "general:muc-luc-tra-cuu-biet-duoc-va-hoat-chat",
        "leaflet:thuoc:hapacol-250-dhg-11500",
        "leaflet:thuoc:panadol-extra-gsk-150-vien-11440",
    ]
    assert [document.kind for document in bundle.documents] == [
        DocumentKind.DRUG_MONOGRAPH,
        DocumentKind.GENERAL_MONOGRAPH,
        DocumentKind.LEAFLET,
        DocumentKind.LEAFLET,
    ]
    assert bundle.documents[0].source.url is None
    assert bundle.documents[2].source == SourceInfo(
        title="Tờ hướng dẫn sử dụng",
        url=None,
    )
    assert [section.key for section in bundle.sections] == [
        DOSAGE,
        "drug:paracetamol:chong-chi-dinh",
        BRAND_INDEX_SECTION_ID,
        HAPACOL,
        PANADOL,
    ]
    assert [section.ordinal for section in bundle.sections] == [1, 2, 1, 1, 1]
    assert result.skipped_sections == ()
    assert result.manifest.schema_version == BUNDLE_SCHEMA_VERSION
    assert result.manifest.collection == BundleCollection(
        key=COLLECTION_KEY, title=COLLECTION_TITLE
    )
    assert (result.manifest.document_count, result.manifest.section_count) == (4, 5)
    # The chunking is written out, so the bundle says how the backend will chunk it.
    assert result.manifest.chunking == BundleChunking()
    written = json.loads((tmp_path / "bundle" / "manifest.json").read_text("utf-8"))
    assert written["chunking"] == BundleChunking().model_dump(mode="json")
    assert result.manifest.generator.name == "pharma-lab"
    assert result.manifest.generator.build_id == "fixture-build-0001"
    assert result.manifest.source_digests == {
        "source_pdf_sha256": "1" * 64,
        "leaflet_source_manifest_sha256": "2" * 64,
        "leaflet_source_file_count": "2",
        "curated_curated_tables_sha256": "5" * 64,
        "curated_glossary_sha256": "6" * 64,
        "curated_mappings_sha256": "7" * 64,
        "curated_table_overrides_sha256": "8" * 64,
    }


def test_export_maps_block_kinds_retrieval_and_pages(tmp_path: Path) -> None:
    _, bundle = _export(tmp_path)
    sections = {section.key: section for section in bundle.sections}

    dosage = sections[DOSAGE]
    assert [block.kind for block in dosage.blocks] == [BlockKind.PROSE, BlockKind.TABLE]
    assert dosage.blocks[1].table_key == "curated-table-1134-001"
    assert (dosage.blocks[1].start_page, dosage.blocks[1].end_page) == (1134, 1134)
    assert (dosage.start_page, dosage.end_page) == (1133, 1134)
    assert dosage.heading == "Liều lượng và cách dùng"
    assert dosage.context_path == ["Liều lượng và cách dùng"]

    index = sections[BRAND_INDEX_SECTION_ID]
    assert [block.kind for block in index.blocks] == [BlockKind.INDEX_ENTRIES]

    leaflet = sections[PANADOL]
    assert (leaflet.start_page, leaflet.end_page) == (None, None)
    # The page title and the own heading line are dropped; the table opens the body.
    assert [block.kind for block in leaflet.blocks] == [
        BlockKind.TABLE,
        BlockKind.PROSE,
    ]
    assert [block.start_page for block in leaflet.blocks] == [None, None]
    assert leaflet.blocks[0].markdown.startswith("| Thông tin thành phần")
    assert not any(b.markdown.startswith("# ") for b in leaflet.blocks)

    assert block_kind_for(ATC_SECTION_ID, "paragraph") is BlockKind.LIST
    assert block_kind_for(ATC_SECTION_ID, "table") is BlockKind.TABLE


def test_export_copies_glossary_and_attaches_mappings(tmp_path: Path) -> None:
    _, bundle = _export(tmp_path)
    mappings = {mapping.key: mapping for mapping in bundle.colloquial_mappings}

    assert len(mappings) == len(bundle.colloquial_mappings)
    assert [entry.term for entry in bundle.glossary] == ["ADR", "NSAID"]
    assert mappings["panadol-extra-gsk-150-vien-11440"] == ColloquialMappingRecord(
        key="panadol-extra-gsk-150-vien-11440",
        aliases=["Panadol đỏ", "Panadol extra đỏ", "Panadol vỉ đỏ", "Panadol hộp đỏ"],
        visual_sign="Hộp màu đỏ, vỉ thuốc màu đỏ",
        product_names=["Panadol Extra GSK"],
        section_keys=[PANADOL],
    )
    assert mappings["hapacol-250-dhg-11500"] == ColloquialMappingRecord(
        key="hapacol-250-dhg-11500",
        product_names=["Hapacol 250 DHG"],
        section_keys=[HAPACOL],
    )


def test_export_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    export_bundle(_request(tmp_path / "bundle"))

    with pytest.raises(FileExistsError, match="--force"):
        export_bundle(_request(tmp_path / "bundle"))
    replaced = export_bundle(_request(tmp_path / "bundle", force=True))
    assert replaced.manifest.section_count == 5


def test_leaflet_blocks_keep_pipe_tables_apart() -> None:
    rows = "\n".join(f"| thuốc {index} | {'x' * 40} |" for index in range(3))
    table = f"| Thành phần | Hàm lượng |\n| --- | --- |\n{rows}"

    blocks = leaflet_blocks(f"# Thuốc\n\nĐoạn một.\n\n{table}\n\n\nĐoạn hai.")

    assert [block.kind for block in blocks] == [
        BlockKind.PROSE,
        BlockKind.TABLE,
        BlockKind.PROSE,
    ]
    assert blocks[0].markdown == "# Thuốc\n\nĐoạn một."
    assert blocks[1].markdown == table
    assert blocks[2].markdown == "Đoạn hai."


def test_iter_document_chunks_runs_backend_chunker(tmp_path: Path) -> None:
    _, bundle = _export(tmp_path)

    items = list(iter_document_chunks(bundle))

    assert [item.document.key for item in items] == [d.key for d in bundle.documents]
    assert [s.key for item in items for s in item.sections] == [
        s.key for s in bundle.sections
    ]
    assert [draft.ordinal for draft in items[0].drafts] == list(
        range(1, len(items[0].drafts) + 1)
    )
    assert gold_chunk_label("drug:paracetamol", 2) == "drug:paracetamol:chunk-002"


def test_collection_title_describes_the_content() -> None:
    assert COLLECTION_TITLE == (
        "Dược thư Quốc gia Việt Nam và tờ hướng dẫn sử dụng thuốc"
    )


EFFERALGAN = "leaflet:thuoc:efferalgan-500-11600"
_EFFERALGAN_TITLE = "Efferalgan 500 mg (hộp 16 viên)"


def _subsection_row(index: int, heading: str, slug: str, body: str) -> dict:
    return {
        "id": f"{EFFERALGAN}:{index:02d}-{slug}",
        "page_id": EFFERALGAN,
        "content_type": "brand_page",
        "title": _EFFERALGAN_TITLE,
        "section": heading,
        "text": f"# {_EFFERALGAN_TITLE}\n\n### {index}. {heading}\n\n{body}",
        "source": "Tờ hướng dẫn sử dụng",
        "context_path": [heading],
        "context_header": f"{_EFFERALGAN_TITLE}\n> {heading}",
        "colloquial_mapping": {"product_names": ["Efferalgan 500 mg"]},
        "start_page": 0,
        "end_page": 0,
        "warnings": [],
        "hydrate_strategy": "full_section",
        "section_char_count": 80,
    }


def test_export_groups_leaflet_subsections_under_one_document(tmp_path: Path) -> None:
    rag_final = tmp_path / "rag-final"
    shutil.copytree(FIXTURE, rag_final)
    with (rag_final / "sections.jsonl").open("a", encoding="utf-8") as handle:
        for row in (
            _subsection_row(1, "Thành phần", "thanh-phan", "Paracetamol 500 mg."),
            _subsection_row(
                2, "Cách dùng - Liều dùng", "cach-dung-lieu-dung", "1 viên mỗi 6 giờ."
            ),
        ):
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    export_bundle(
        ExportRequest(
            rag_final_dir=rag_final,
            glossary_path=FIXTURE / "term_glossary.json",
            mappings_path=FIXTURE / "colloquial_mappings.json",
            output_dir=tmp_path / "bundle",
        )
    )
    bundle = read_bundle(tmp_path / "bundle")

    documents = {document.key: document for document in bundle.documents}
    assert documents[EFFERALGAN].kind is DocumentKind.LEAFLET
    assert documents[EFFERALGAN].title == _EFFERALGAN_TITLE
    subsections = [s for s in bundle.sections if s.document_key == EFFERALGAN]
    assert [s.key for s in subsections] == [
        f"{EFFERALGAN}:01-thanh-phan",
        f"{EFFERALGAN}:02-cach-dung-lieu-dung",
    ]
    assert [s.ordinal for s in subsections] == [1, 2]
    assert subsections[1].heading == "Cách dùng - Liều dùng"
    assert subsections[1].context_path == ["Cách dùng - Liều dùng"]
    mapping = next(
        m
        for m in bundle.colloquial_mappings
        if f"{EFFERALGAN}:01-thanh-phan" in m.section_keys
    )
    assert f"{EFFERALGAN}:02-cach-dung-lieu-dung" in mapping.section_keys
    assert mapping.product_names.count("Efferalgan 500 mg") == 1


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Xem mục Quá liều và xử trí.", True),
        ("Xem phần Cách dùng ở trên.", True),
        ("Thuốc thuộc danh mục bảo hiểm y tế thanh toán.", False),
        ("Ziagen.", False),
        ("Ngừng thuốc. " + "Theo dõi chức năng gan. " * 10, False),
    ],
)
def test_sections_that_only_point_elsewhere_are_left_out(
    text: str, expected: bool
) -> None:
    assert is_cross_reference_only(text) is expected


def test_a_leaflet_row_without_page_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="page_id"):
        document_for_section(
            {
                "id": "leaflet:thuoc:x:01-thanh-phan",
                "title": "X",
                "section": "Thành phần",
            }
        )


def test_leaflet_body_drops_the_page_title_and_the_own_heading_line() -> None:
    text = "# Abanuti 1 g\n\n### 1. Thành phần\n\nLevocarnitin 1,0 g."
    assert leaflet_body(text) == "Levocarnitin 1,0 g."
    assert leaflet_body("# X\n\n#### - Quá liều\n\nGây tiêu chảy.") == "Gây tiêu chảy."
    assert leaflet_body("Chỉ một đoạn.") == "Chỉ một đoạn."
