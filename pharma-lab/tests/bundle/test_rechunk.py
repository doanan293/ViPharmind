from pathlib import Path

import pytest
from pharma_agent.domain.corpus.bundle import (
    BundleChunking,
    BundleCollection,
    read_bundle,
)

from pharma_lab.bundle.chunks import iter_document_chunks
from pharma_lab.bundle.export import ExportRequest, export_bundle
from pharma_lab.bundle.rechunk import RechunkRequest, rechunk_bundle

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "rag_final_small"


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


def _request(source: Path, output: Path) -> RechunkRequest:
    return RechunkRequest(
        bundle_dir=source,
        output_dir=output,
        collection_key="formulary_sections",
        collection_title="Một chunk mỗi mục",
        target_chars=1,
    )


def test_rechunk_copies_the_content_under_a_new_collection_and_chunking(
    tmp_path: Path,
) -> None:
    source = _bundle_dir(tmp_path)
    original = read_bundle(source)

    manifest = rechunk_bundle(_request(source, tmp_path / "sections"))

    rechunked = read_bundle(tmp_path / "sections")
    assert manifest == rechunked.manifest
    assert rechunked.manifest.collection == BundleCollection(
        key="formulary_sections", title="Một chunk mỗi mục"
    )
    assert rechunked.manifest.chunking == BundleChunking(target_chars=1)
    # Vectors belong to the old chunks; `bundle embed` adds the new ones.
    assert rechunked.manifest.embeddings == []
    assert not (tmp_path / "sections" / "embeddings").exists()
    assert rechunked.manifest.source_digests == original.manifest.source_digests
    assert rechunked.manifest.generator == original.manifest.generator
    assert (rechunked.documents, rechunked.sections) == (
        original.documents,
        original.sections,
    )
    assert (rechunked.glossary, rechunked.colloquial_mappings) == (
        original.glossary,
        original.colloquial_mappings,
    )


def test_chunks_of_a_rechunked_bundle_follow_its_manifest(tmp_path: Path) -> None:
    source = _bundle_dir(tmp_path)
    rechunk_bundle(_request(source, tmp_path / "sections"))

    packed = [
        draft
        for document in iter_document_chunks(read_bundle(source))
        for draft in document.drafts
    ]
    per_section = [
        draft
        for document in iter_document_chunks(read_bundle(tmp_path / "sections"))
        for draft in document.drafts
    ]

    assert len(per_section) > len(packed)
    assert all(len(draft.section_keys) == 1 for draft in per_section)


def test_rechunk_refuses_to_overwrite_its_source(tmp_path: Path) -> None:
    source = _bundle_dir(tmp_path)

    with pytest.raises(ValueError, match="must differ"):
        rechunk_bundle(_request(source, source))


def test_rechunk_without_enrichment_indexes_the_bare_chunk_text(tmp_path: Path) -> None:
    source = _bundle_dir(tmp_path)
    manifest = rechunk_bundle(
        RechunkRequest(
            bundle_dir=source,
            output_dir=tmp_path / "plain",
            collection_key="formulary_plain",
            collection_title="Không enrichment",
            enrichment=False,
        )
    )

    assert manifest.chunking == BundleChunking(enrichment=False)
    enriched = [
        draft
        for document in iter_document_chunks(read_bundle(source))
        for draft in document.drafts
    ]
    plain = [
        draft
        for document in iter_document_chunks(read_bundle(tmp_path / "plain"))
        for draft in document.drafts
    ]
    # Same reading units, only the indexed text loses its enrichment.
    assert [d.chunk_text for d in plain] == [d.chunk_text for d in enriched]
    assert all(d.embedding_text == d.chunk_text for d in plain)
    assert any(d.embedding_text != d.chunk_text for d in enriched)
