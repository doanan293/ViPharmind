import uuid

import pytest

from pharma_agent.domain.corpus.chunking import CHUNKER_VERSION
from pharma_agent.domain.corpus.identity import CORPUS_NAMESPACE
from pharma_agent.domain.corpus.models import (
    CorpusImportError,
    Release,
    ReleaseStatus,
    Visibility,
    build_snapshot,
    bundle_digest,
    collection_id_for,
    document_id_for,
    releases_to_retire,
    section_id_for,
)
from pharma_agent.domain.corpus.ports import Embedder
from tests.corpus_fixtures import (
    DOSAGE_SECTION,
    LEAFLET,
    LEAFLET_SECTION,
    PARACETAMOL,
    PHARMACOLOGY_SECTION,
    embedding_texts,
    small_bundle,
    small_bundle_embeddings,
    with_section_text,
)
from tests.fakes import (
    FAKE_EMBEDDING_DIMENSION,
    FAKE_EMBEDDING_MODEL,
    NOW,
    FakeEmbedder,
)


def test_snapshot_maps_the_fixture_to_rows() -> None:
    bundle = small_bundle()
    snapshot = build_snapshot(bundle)

    assert snapshot.collection.id == collection_id_for("formulary")
    # A bundle carries no owner: imported as is, it is the public system corpus.
    assert snapshot.collection.visibility is Visibility.PUBLIC
    assert snapshot.collection.is_system
    assert snapshot.collection.current_release_id is None
    assert [document.key for document in snapshot.documents] == [PARACETAMOL, LEAFLET]
    assert len(snapshot.sections) == 5
    assert not hasattr(snapshot, "revisions")
    assert len(snapshot.chunks) == len(snapshot.release_chunks) >= 2
    assert {chunk.chunker_version for chunk in snapshot.chunks} == {CHUNKER_VERSION}
    assert snapshot.chunker_version == CHUNKER_VERSION
    assert snapshot.bundle_digest == bundle_digest(bundle)

    document_ids = {document.key: document.id for document in snapshot.documents}
    chunks = {chunk.id: chunk for chunk in snapshot.chunks}
    assert {chunk.document_id for chunk in snapshot.chunks} == set(
        document_ids.values()
    )
    # Every section of the bundle lands in a chunk of its document; a section longer
    # than MAX_CHUNK_CHARS spans several chunks that each name it.
    placed = {key for chunk in snapshot.chunks for key in chunk.section_keys}
    assert placed == {section.key for section in snapshot.sections}
    assert sum(PHARMACOLOGY_SECTION in c.section_keys for c in snapshot.chunks) > 1
    placements = {(p.document_id, p.ordinal) for p in snapshot.release_chunks}
    assert len(placements) == len(snapshot.release_chunks)
    for placement in snapshot.release_chunks:
        chunk = chunks[placement.chunk_version_id]
        assert (chunk.document_id, chunk.ordinal) == (
            placement.document_id,
            placement.ordinal,
        )
    dosage = next(c for c in snapshot.chunks if DOSAGE_SECTION in c.section_keys)
    assert dosage.context_header.startswith("Paracetamol > ")
    assert "Liều lượng và cách dùng" in dosage.headings
    leaflet = next(c for c in snapshot.chunks if LEAFLET_SECTION in c.section_keys)
    assert leaflet.colloquial is not None and leaflet.colloquial.key == "panadol-extra"

    assert set(embedding_texts(snapshot)) == set(
        small_bundle_embeddings(FAKE_EMBEDDING_MODEL, FAKE_EMBEDDING_DIMENSION)
    )
    stats = snapshot.stats()
    assert (stats.documents, stats.sections) == (2, 5)
    assert not hasattr(stats, "section_revisions")
    assert (stats.glossary_entries, stats.colloquial_mappings) == (2, 1)
    assert stats.chunks == len(snapshot.release_chunks)
    assert stats.embeddings_computed == stats.points_upserted == 0


def test_snapshot_ids_are_deterministic_and_follow_content() -> None:
    first = build_snapshot(small_bundle())
    assert build_snapshot(small_bundle()) == first

    edited = build_snapshot(
        with_section_text(small_bundle(), DOSAGE_SECTION, "Ghi chú mới.")
    )
    assert {s.id for s in edited.sections} == {s.id for s in first.sections}
    chunks_before = {c.id: c for c in first.chunks}
    chunks_after = {c.id: c for c in edited.chunks}
    untouched_before = {
        c.id for c in first.chunks if DOSAGE_SECTION not in c.section_keys
    }
    untouched_after = {
        c.id for c in edited.chunks if DOSAGE_SECTION not in c.section_keys
    }
    assert untouched_before == untouched_after
    assert set(chunks_before) != set(chunks_after)
    assert [c.ordinal for c in first.release_chunks] == [
        c.ordinal for c in edited.release_chunks
    ]


def test_bundle_digest_tracks_content_not_embeddings() -> None:
    bundle = small_bundle()
    digest = bundle_digest(bundle)
    assert len(digest) == 64
    assert bundle_digest(bundle.model_copy(update={"embeddings": {}})) == digest
    assert (
        bundle_digest(with_section_text(bundle, DOSAGE_SECTION, "Ghi chú.")) != digest
    )


def test_snapshot_rejects_unknown_document_reference() -> None:
    bundle = small_bundle()
    broken = bundle.model_copy(
        update={
            "sections": [
                bundle.sections[0].model_copy(update={"document_key": "drug:missing"})
            ]
        }
    )
    with pytest.raises(CorpusImportError, match="drug:missing"):
        build_snapshot(broken)


def test_identity_helpers_are_uuid5_in_the_corpus_namespace() -> None:
    collection_id = collection_id_for("formulary")
    document_id = document_id_for(collection_id, PARACETAMOL)
    assert collection_id == uuid.uuid5(CORPUS_NAMESPACE, "collection\x1fformulary")
    assert document_id == uuid.uuid5(
        CORPUS_NAMESPACE, f"document\x1f{collection_id}\x1f{PARACETAMOL}"
    )
    assert section_id_for(document_id, DOSAGE_SECTION) == uuid.uuid5(
        CORPUS_NAMESPACE, f"section\x1f{document_id}\x1f{DOSAGE_SECTION}"
    )


def _release(number: int, status: ReleaseStatus = ReleaseStatus.READY) -> Release:
    return Release(
        id=uuid.uuid4(),
        collection_id=collection_id_for("formulary"),
        number=number,
        status=status,
        bundle_digest="0" * 64,
        chunker_version=CHUNKER_VERSION,
        embedding_model=FAKE_EMBEDDING_MODEL,
        created_at=NOW,
    )


def test_releases_to_retire_keeps_current_and_newest() -> None:
    r1, r3, r4, r5 = _release(1), _release(3), _release(4), _release(5)
    r2 = _release(2, ReleaseStatus.RETIRED)
    releases = [r1, r2, r3, r4, r5]
    assert releases_to_retire(releases, r1.id, keep=2) == [r3]
    assert releases_to_retire(releases, r1.id, keep=0) == [r5, r4, r3]
    assert releases_to_retire(releases, None, keep=10) == []
    with pytest.raises(ValueError, match="keep"):
        releases_to_retire(releases, None, keep=-1)


async def test_fake_embedder_satisfies_the_embedder_port() -> None:
    embedder: Embedder = FakeEmbedder()
    assert (embedder.model, embedder.dimension) == (FAKE_EMBEDDING_MODEL, 4)
    assert len((await embedder.embed(["x"]))[0]) == embedder.dimension
