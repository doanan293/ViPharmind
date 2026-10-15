from pathlib import Path

from pharma_agent.domain.corpus.bundle import read_bundle

from pharma_lab.bundle.evaluation_chunks import (
    evaluation_chunk_rows,
    write_evaluation_chunks,
)
from pharma_lab.bundle.export import ExportRequest, export_bundle

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "rag_final_small"
FIELDS_READ_BY_THE_BUILDERS = (
    "chunk_id",
    "document_id",
    "ordinal",
    "section_ids",
    "headings",
    "title",
    "source",
    "content_type",
    "context_header",
    "chunk_text",
    "embedding_text",
    "has_table",
    "has_list",
    "structured_section_ids",
    "colloquial_mapping",
    "term_annotations",
)


def _bundle_dir(tmp_path: Path) -> Path:
    export_bundle(
        ExportRequest(
            rag_final_dir=FIXTURE,
            glossary_path=FIXTURE / "term_glossary.json",
            mappings_path=FIXTURE / "colloquial_mappings.json",
            output_dir=tmp_path / "bundle",
        )
    )
    return tmp_path / "bundle"


def test_rows_name_the_document_and_every_section_in_the_chunk(tmp_path: Path) -> None:
    bundle = read_bundle(_bundle_dir(tmp_path))
    rows = evaluation_chunk_rows(bundle)

    assert rows and all(set(row) == set(FIELDS_READ_BY_THE_BUILDERS) for row in rows)
    for row in rows:
        assert row["chunk_id"] == f"{row['document_id']}:chunk-{row['ordinal']:03d}"
        assert row["section_ids"] and len(row["section_ids"]) == len(row["headings"])
    placed = {key for row in rows for key in row["section_ids"]}
    assert placed == {section.key for section in bundle.sections}
    packed = next(row for row in rows if len(row["section_ids"]) > 1)
    assert packed["context_header"].count(";") == len(packed["headings"]) - 1
    assert "hydrate_strategy" not in rows[0] and "chunk_role" not in rows[0]


def test_structure_flags_follow_the_block_kinds_of_the_packed_sections(
    tmp_path: Path,
) -> None:
    bundle = read_bundle(_bundle_dir(tmp_path))
    kinds = {
        section.key: {block.kind.value for block in section.blocks}
        for section in bundle.sections
    }
    for row in evaluation_chunk_rows(bundle):
        held = set().union(*(kinds[key] for key in row["section_ids"]))
        assert row["has_table"] == ("table" in held)
        assert row["has_list"] == bool(held & {"list", "index_entries"})
        assert row["structured_section_ids"] == [
            key
            for key in row["section_ids"]
            if kinds[key] & {"table", "list", "index_entries"}
        ]


def test_write_evaluation_chunks_writes_one_row_per_chunk(tmp_path: Path) -> None:
    bundle = read_bundle(_bundle_dir(tmp_path))
    path = tmp_path / "work" / "chunks.jsonl"

    count = write_evaluation_chunks(bundle, path)

    assert count == len(evaluation_chunk_rows(bundle))
    assert len(path.read_text("utf-8").splitlines()) == count
