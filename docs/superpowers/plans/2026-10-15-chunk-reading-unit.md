# Chunk là đơn vị đọc: gộp mục, bỏ hydrate, 5 chunk mỗi lượt

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chunk trở thành đúng văn bản LLM đọc: chunker gộp các mục liền kề của một tài liệu tới khoảng 1.024 token, backend bỏ hẳn hydrate, reranker trả 5 chunk mỗi lượt, mọi nhãn và dữ liệu đánh giá đi theo.

**Architecture:** Backend (`pharma_agent`) là chunker duy nhất: `chunk_document` gộp mục, chunk version trỏ thẳng tài liệu và mang `section_keys`; retrieval trả `Hit` đã đủ text nên `Hydrator`, `section_revisions` và cột `hydrate_strategy` bị gỡ (migration 0021). pharma-lab dùng lại chunker đó để sinh chunk đánh giá với nhãn `<document_key>:chunk-NNN`; benchmark và golden giữ gold theo section, một chunk trúng khi chứa mục gold. Pipeline rag-final chỉ còn `sections.jsonl` và `blocks.jsonl`.

**Tech Stack:** Python 3.13, uv workspace (`backend`, `pharma-lab`), pydantic, SQLAlchemy async, Alembic, Qdrant, pytest; frontend React Router với orval.

**Spec:** `docs/superpowers/specs/2026-10-14-paper-v2-design.md` §3.0c (và §0 về không giữ legacy).

## Global Constraints

- Không giữ đường tương thích ngược: không cờ, không nhánh "legacy", không migration dữ liệu cũ; DB production xuất phát trống (spec §0, §3.0c).
- `TARGET_CHUNK_CHARS = 3200`, `MAX_CHUNK_CHARS = 5600`, `CHUNKER_VERSION = "chunker-v2"` (spec §3.0c).
- `rerank.top_n = 5`, `max_evidence_chars = 60000` (evidence tích luỹ tới 15 chunk qua 3 vòng, `pack` xếp theo điểm rerank xuyên vòng); mọi chỗ "top 8" thành 5 (spec §3.0c).
- Nhãn gold chunk `<document_key>:chunk-NNN`, NNN một-based ba chữ số (spec §3.0c).
- Nhóm benchmark `chunk_risk` đổi tên `structured`, quota 1.000; golden schema `e2e-golden-v3`, không `gold_chunk_ids` (spec §3.0c).
- `PIPELINE_VERSION` (version của `pharma-lab` trong `pharma-lab/pyproject.toml`) lên `0.4.0` (spec §3.0c).
- Gate trước mỗi commit, chạy ở `pharma-lab/` và `backend/`: `uv run ruff check src tests && uv run ruff format src tests && uv run pyrefly check --min-severity warn && uv run pytest -q`. Commit không có trailer Co-Authored-By.
- Lệnh dài (build corpus, evaluation build, đo token) chạy trong tmux.

## Review Focus

1. Một mục dài hơn `MAX_CHUNK_CHARS` phải cho ra nhiều chunk chỉ của mục đó, và mục đứng sau nó không bị gộp vào phần cuối của nó (Task 1, test `test_oversized_section_splits_alone`).
2. Mục có mọi block rỗng không được tạo chunk rỗng và không được chen `## heading` trống vào chunk kế (Task 1, test `test_blank_section_yields_nothing`).
3. Câu `multi_required` mà hai mục gold nằm trong cùng một chunk: chunk đó phải thoả cả hai đơn vị, nDCG không thấp hơn khi hai mục nằm ở hai chunk riêng (ideal cố định mỗi câu, một đơn vị mỗi hạng từ hạng 1, chặn ở 1) (Task 5, test `test_one_chunk_satisfies_several_units`).
4. Nhãn relevance chấp nhận chunk ngoài mục gold phải vẫn tính trúng khi chunk mang nhiều mục (Task 5, test `test_accepted_chunk_counts_as_hit`).
5. Gói evidence không bao giờ cắt text: khi 5 chunk vượt `max_evidence_chars`, chunk điểm thấp nhất bị bỏ nguyên khối (Task 3, test `test_pack_drops_whole_chunks_never_truncates`).

---

### Task 1: Chunker gộp mục trong backend

**Files:**
- Modify: `backend/src/pharma_agent/domain/corpus/chunking.py`
- Modify: `backend/src/pharma_agent/domain/corpus/identity.py` (bỏ `section_revision_id`, đổi tham số `chunk_version_id`)
- Modify: `backend/src/pharma_agent/domain/corpus/__init__.py` (export `chunk_document`, bỏ `chunk_section`, `hydrate_strategy_for`)
- Delete: `backend/src/pharma_agent/domain/corpus/hydrate.py`, `backend/tests/domain/corpus/test_hydrate.py`
- Test: `backend/tests/domain/corpus/test_chunking.py`, `backend/tests/domain/corpus/test_identity.py`, golden `backend/tests/domain/corpus/golden/chunking_v2.json` (thay `chunking_v1.json`)

**Interfaces:**
- Produces: `chunk_document(document: DocumentRecord, sections: Sequence[SectionRecord], glossary, mappings, *, target_chars=TARGET_CHUNK_CHARS, max_chars=MAX_CHUNK_CHARS) -> list[ChunkDraft]`; `ChunkDraft(chunk_version_id, document_key, ordinal, section_keys: list[str], headings: list[str], chunk_text, context_header, embedding_text, embedding_text_sha256, start_page, end_page, term_annotations, colloquial)`; `chunk_version_id(document_key, chunk_text, embedding_text, chunker_version)`; hằng `TARGET_CHUNK_CHARS`, `MAX_CHUNK_CHARS`, `CHUNKER_VERSION`.

- [ ] **Step 1: Viết test fail cho cách gộp**

Thêm vào `backend/tests/domain/corpus/test_chunking.py` (giữ các import có sẵn của file, thay `chunk_section` bằng `chunk_document`):

```python
from pharma_agent.domain.corpus.bundle import (
    BlockKind,
    BlockRecord,
    DocumentRecord,
    SectionRecord,
)
from pharma_agent.domain.corpus.chunking import (
    CHUNKER_VERSION,
    MAX_CHUNK_CHARS,
    TARGET_CHUNK_CHARS,
    chunk_document,
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
    return DocumentRecord.model_validate(
        {
            "key": "drug:paracetamol",
            "kind": "drug_monograph",
            "title": "Paracetamol",
            "source": {"title": "Dược thư", "kind": "formulary"},
        }
    )


def test_short_sections_pack_into_one_chunk_in_document_order() -> None:
    sections = [
        _section("drug:paracetamol:chi-dinh", "Chỉ định", "Giảm đau.", 1),
        _section("drug:paracetamol:lieu-dung", "Liều dùng", "500 mg.", 2),
    ]
    (chunk,) = chunk_document(_document(), sections, [], [])
    assert chunk.section_keys == [s.key for s in sections]
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
    assert len(middle) >= 2 and all(
        len(c.chunk_text) <= MAX_CHUNK_CHARS for c in middle
    )
    assert middle[0].chunk_text.startswith("## Mục 2\n\n")
    assert chunks[-1].section_keys == ["drug:paracetamol:s3"]


def test_blank_section_yields_nothing() -> None:
    sections = [
        _section("drug:paracetamol:s1", "Mục 1", "   ", 1),
        _section("drug:paracetamol:s2", "Mục 2", "có chữ", 2),
    ]
    (chunk,) = chunk_document(_document(), sections, [], [])
    assert chunk.section_keys == ["drug:paracetamol:s2"]
    assert "Mục 1" not in chunk.chunk_text


def test_chunk_identity_changes_with_the_chunker_version() -> None:
    sections = [_section("drug:paracetamol:s1", "Mục 1", "có chữ", 1)]
    (chunk,) = chunk_document(_document(), sections, [], [])
    assert CHUNKER_VERSION == "chunker-v2"
    assert chunk.embedding_text.startswith("Paracetamol > Mục 1")
```

Golden test: đổi `chunking_v1.json` thành `chunking_v2.json` với cùng input (glossary, mappings, document, sections) nhưng output là danh sách chunk của `chunk_document`; bước 4 sinh lại file bằng cách chạy test ở chế độ ghi (`UPDATE_GOLDEN=1`) nếu test đang có cơ chế đó, nếu không thì ghi bằng một đoạn script nhỏ trong test module (`python -c`), rồi kiểm tra bằng mắt rằng số chunk giảm và `section_keys` có nhiều phần tử.

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && uv run pytest tests/domain/corpus/test_chunking.py -q`
Expected: FAIL `ImportError: cannot import name 'chunk_document'`.

- [ ] **Step 3: Viết chunker mới**

Trong `chunking.py`, giữ `split_oversized_paragraph`, `split_long_text`, `split_table_markdown`, `split_lines_without_breaking_entries`; thay `MAX_CHUNK_CHARS`, `ChunkDraft`, `_split_block`, `_context_header`, `chunk_section` bằng:

```python
CHUNKER_VERSION = "chunker-v2"
# About 1,024 Qwen3 tokens at the 3.1 chars per token measured on the corpus; a chunk
# grows by whole sections until the next one would pass this.
TARGET_CHUNK_CHARS = 3200
# A single section longer than this is split on its own; with the context header the
# longest chunk stays under the 2,048-token embedding slot.
MAX_CHUNK_CHARS = 5600


class ChunkDraft(BaseModel):
    """One chunk of a document: whole consecutive sections, or one part of a long section."""

    model_config = ConfigDict(frozen=True)

    chunk_version_id: uuid.UUID
    document_key: str
    ordinal: int
    section_keys: list[str]
    headings: list[str]
    chunk_text: str
    context_header: str
    embedding_text: str
    embedding_text_sha256: str
    start_page: int | None
    end_page: int | None
    term_annotations: list[TermAnnotation]
    colloquial: ColloquialMapping | None


def _split_block(kind: BlockKind, text: str, max_chars: int) -> list[str]:
    if kind is BlockKind.TABLE:
        return split_table_markdown(text, max_chars)
    if kind is BlockKind.LIST or kind is BlockKind.INDEX_ENTRIES:
        return split_lines_without_breaking_entries(text, max_chars)
    return split_long_text(text, max_chars)


def section_text(section: SectionRecord) -> str:
    """The section as the model reads it: its heading, then its blocks; empty when blank."""
    body = "\n\n".join(b.markdown.strip() for b in section.blocks if b.markdown.strip())
    if not body:
        return ""
    heading = section.heading.strip()
    return f"## {heading}\n\n{body}" if heading else body


def _context_header(title: str, headings: Sequence[str]) -> str:
    names = [h.strip() for h in headings if h.strip()]
    title_text = title.strip()
    if title_text and names:
        return f"{title_text} > {'; '.join(names)}"
    return title_text or "; ".join(names)


def _pages(sections: Sequence[SectionRecord]) -> tuple[int | None, int | None]:
    starts = [s.start_page for s in sections if s.start_page is not None]
    ends = [s.end_page for s in sections if s.end_page is not None]
    return (min(starts) if starts else None, max(ends) if ends else None)


def _section_parts(section: SectionRecord, max_chars: int) -> list[str]:
    """A long section as several texts, each under max_chars and each led by the heading."""
    text = section_text(section)
    if len(text) <= max_chars:
        return [text]
    heading = f"## {section.heading.strip()}\n\n" if section.heading.strip() else ""
    parts: list[str] = []
    for block in section.blocks:
        raw = block.markdown.strip()
        if raw:
            parts.extend(_split_block(block.kind, raw, max_chars - len(heading)))
    return [heading + part for part in parts]


def chunk_document(
    document: DocumentRecord,
    sections: Sequence[SectionRecord],
    glossary: Sequence[GlossaryEntry],
    mappings: Sequence[ColloquialMappingRecord],
    *,
    target_chars: int = TARGET_CHUNK_CHARS,
    max_chars: int = MAX_CHUNK_CHARS,
) -> list[ChunkDraft]:
    """Pack a document's sections, in order, into chunks of about target_chars."""
    ordered = sorted(sections, key=lambda s: s.ordinal)
    groups: list[tuple[list[SectionRecord], str]] = []
    current: list[SectionRecord] = []
    current_text = ""

    def flush() -> None:
        nonlocal current, current_text
        if current:
            groups.append((current, current_text))
        current, current_text = [], ""

    for section in ordered:
        text = section_text(section)
        if not text:
            continue
        if len(text) > max_chars:
            flush()
            groups.extend(
                ([section], part) for part in _section_parts(section, max_chars)
            )
            continue
        if current and len(current_text) + 2 + len(text) > target_chars:
            flush()
        current_text = f"{current_text}\n\n{text}" if current_text else text
        current.append(section)
    flush()

    drafts: list[ChunkDraft] = []
    for ordinal, (members, chunk_text) in enumerate(groups, start=1):
        headings = [m.heading for m in members]
        context_header = _context_header(document.title, headings)
        colloquial = next(
            (c for c in (mapping_for_section(m.key, mappings) for m in members) if c),
            None,
        )
        searchable = (
            f"{context_header}\n\n{chunk_text}" if context_header else chunk_text
        )
        terms = detect_terms(searchable, glossary)
        embedding_text = compose_embedding_text(
            context_header=context_header,
            chunk_text=chunk_text,
            colloquial=colloquial,
            terms=terms,
        )
        start_page, end_page = _pages(members)
        drafts.append(
            ChunkDraft(
                chunk_version_id=chunk_version_id(
                    document.key, chunk_text, embedding_text, CHUNKER_VERSION
                ),
                document_key=document.key,
                ordinal=ordinal,
                section_keys=[m.key for m in members],
                headings=headings,
                chunk_text=chunk_text,
                context_header=context_header,
                embedding_text=embedding_text,
                embedding_text_sha256=sha256_hex(embedding_text),
                start_page=start_page,
                end_page=end_page,
                term_annotations=terms,
                colloquial=colloquial,
            )
        )
    return drafts
```

Trong `identity.py`: xoá `section_revision_id`; đổi chữ ký `chunk_version_id(document_key: str, chunk_text: str, embedding_text: str, chunker_version: str)` (nội dung hàm giữ nguyên, chỉ đổi tên biến đầu). Xoá `hydrate.py` và test của nó; cập nhật `__init__.py` của package corpus. `test_identity.py`: bỏ test của `section_revision_id`, đổi tên tham số.

- [ ] **Step 4: Chạy test, sinh golden v2, xác nhận pass**

Run: `cd backend && uv run pytest tests/domain/corpus -q`
Expected: PASS; `chunking_v2.json` có mặt, `chunking_v1.json` đã xoá.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pharma_agent/domain/corpus backend/tests/domain/corpus
git commit -m "feat(backend): chunk_document packs consecutive sections into reading-sized chunks"
```

---

### Task 2: Chunk version thuộc tài liệu: snapshot, bảng, migration 0021, Qdrant payload

**Files:**
- Modify: `backend/src/pharma_agent/domain/corpus/models.py` (`ChunkVersion`, `ReleaseChunk`, `IndexItem`, `ReleaseStats`, `CorpusSnapshot`, `build_snapshot`)
- Modify: `backend/src/pharma_agent/infrastructure/persistence/postgres/corpus_tables.py`
- Create: `backend/src/pharma_agent/infrastructure/persistence/postgres/migrations/versions/0021_chunks_per_document.py`
- Modify: `backend/src/pharma_agent/infrastructure/persistence/postgres/corpus_repository.py` (`stage_release`, `_placement_row`, `index_items`, purge)
- Modify: `backend/src/pharma_agent/infrastructure/retrieval/qdrant_index.py` (`KEYWORD_PAYLOAD_FIELDS`, `point_payload`)
- Modify: `backend/tests/corpus_memory.py`, `backend/tests/corpus_rows.py`, `backend/tests/domain/corpus/test_corpus_models.py`, `backend/tests/infrastructure/test_corpus_repository.py`, `backend/tests/infrastructure/test_qdrant_index.py`, `backend/tests/infrastructure/test_qdrant_adapter.py`, `backend/tests/infrastructure/test_migrations.py`, `backend/tests/infrastructure/test_persistence_metadata.py`

**Interfaces:**
- Consumes: `chunk_document`, `ChunkDraft` (Task 1).
- Produces: `ChunkVersion(id, document_id, ordinal, section_keys, headings, chunk_text, context_header, embedding_text, embedding_text_sha256, start_page, end_page, term_annotations, colloquial, chunker_version)`; `ReleaseChunk(chunk_version_id, document_id, ordinal)`; `IndexItem(chunk_version_id, collection_id, document_id, embedding_text, embedding_text_sha256, release_ids)`; bảng `corpus.chunk_versions(document_id, section_keys text[], headings text[])`, `corpus.release_chunks(release_id, chunk_version_id, document_id, ordinal)`; không còn `corpus.section_revisions`.

- [ ] **Step 1: Viết test fail cho snapshot**

Trong `backend/tests/domain/corpus/test_corpus_models.py` thêm:

```python
def test_snapshot_chunks_belong_to_documents_and_carry_section_keys(
    bundle_small,
) -> None:
    snapshot = build_snapshot(
        collection, bundle_small
    )  # dùng fixture/collection sẵn có của file
    assert not hasattr(snapshot, "revisions")
    chunk = snapshot.chunks[0]
    document_ids = {d.id for d in snapshot.documents}
    assert chunk.document_id in document_ids
    assert chunk.section_keys and all(
        k.startswith(("drug:", "leaflet:", "general:")) for k in chunk.section_keys
    )
    placements = {(p.document_id, p.ordinal) for p in snapshot.release_chunks}
    assert len(placements) == len(snapshot.release_chunks)
    assert snapshot.stats().chunks == len(snapshot.release_chunks)
```

(Thay `bundle_small`/`collection` bằng đúng fixture đang dùng trong file; nếu file dựng bundle thủ công, dùng bundle đó.)

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && uv run pytest tests/domain/corpus/test_corpus_models.py -q`
Expected: FAIL (`revisions` còn tồn tại, `ChunkVersion` chưa có `document_id`).

- [ ] **Step 3: Sửa model và snapshot**

`models.py`: xoá import `hydrate_strategy_for`, `HydrateStrategy`, class `SectionRevision`; `ReleaseStats` bỏ `section_revisions`; `CorpusSnapshot` bỏ `revisions`; thay thân vòng lặp trong `build_snapshot` bằng:

```python
sections_by_document: dict[str, list[SectionRecord]] = defaultdict(list)
for record in bundle.sections:
    section_id = section_id_for(document_ids[record.document_key], record.key)
    sections.append(
        Section(
            id=section_id,
            document_id=document_ids[record.document_key],
            key=record.key,
            heading=record.heading,
        )
    )
    sections_by_document[record.document_key].append(record)
for document_key, members in sections_by_document.items():
    document_id = document_ids[document_key]
    for draft in chunk_document(
        records[document_key], members, bundle.glossary, bundle.colloquial_mappings
    ):
        if draft.chunk_version_id not in chunks:
            chunks[draft.chunk_version_id] = ChunkVersion(
                id=draft.chunk_version_id,
                document_id=document_id,
                ordinal=draft.ordinal,
                section_keys=list(draft.section_keys),
                headings=list(draft.headings),
                chunk_text=draft.chunk_text,
                context_header=draft.context_header,
                embedding_text=draft.embedding_text,
                embedding_text_sha256=draft.embedding_text_sha256,
                start_page=draft.start_page,
                end_page=draft.end_page,
                term_annotations=list(draft.term_annotations),
                colloquial=draft.colloquial,
                chunker_version=CHUNKER_VERSION,
            )
        release_chunks.append(
            ReleaseChunk(
                chunk_version_id=draft.chunk_version_id,
                document_id=document_id,
                ordinal=draft.ordinal,
            )
        )
```

`IndexItem` còn: `chunk_version_id, collection_id, document_id, embedding_text, embedding_text_sha256, release_ids`.

`corpus_tables.py`: xoá `SectionRevisionTable`; `ChunkVersionTable` bỏ `section_revision_id`, `kind`, `table_key`, thêm `document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("corpus.documents.id", ondelete="CASCADE"), nullable=False)`, `section_keys: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)`, `headings: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)` và index `("document_id", "ordinal")`; `ReleaseChunkTable` bỏ `section_id`, `section_revision_id`, `hydrate_strategy`, thêm `document_id` (FK `corpus.documents.id`), index `("release_id", "document_id", "ordinal")`. Cập nhật docstring đầu file.

Migration `0021_chunks_per_document.py` (revision `"0021"`, `down_revision = "0020"`):

```python
def upgrade() -> None:
    # Chunks are re-cut per document; every published release and its citations are rebuilt
    # from the bundle, so the old rows go (the production database starts empty anyway).
    op.execute("DELETE FROM message_citations")
    op.execute("UPDATE corpus.collections SET current_release_id = NULL")
    op.execute("DELETE FROM corpus.release_chunks")
    op.execute("DELETE FROM corpus.chunk_versions")
    op.execute("DELETE FROM corpus.releases")
    op.drop_constraint("strategy", "message_citations", type_="check")
    op.drop_column("message_citations", "strategy")
    op.drop_column("message_citations", "block_chunk_version_ids")
    op.drop_index(
        "ix_release_chunks_release_revision_ordinal",
        table_name="release_chunks",
        schema="corpus",
    )
    op.drop_column("release_chunks", "hydrate_strategy", schema="corpus")
    op.drop_column("release_chunks", "section_revision_id", schema="corpus")
    op.drop_column("release_chunks", "section_id", schema="corpus")
    op.add_column(
        "release_chunks",
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("corpus.documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        schema="corpus",
    )
    op.create_index(
        "ix_release_chunks_release_document_ordinal",
        "release_chunks",
        ["release_id", "document_id", "ordinal"],
        schema="corpus",
    )
    op.drop_column("chunk_versions", "section_revision_id", schema="corpus")
    op.drop_column("chunk_versions", "kind", schema="corpus")
    op.drop_column("chunk_versions", "table_key", schema="corpus")
    op.add_column(
        "chunk_versions",
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("corpus.documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        schema="corpus",
    )
    op.add_column(
        "chunk_versions",
        sa.Column("section_keys", postgresql.ARRAY(sa.Text()), nullable=False),
        schema="corpus",
    )
    op.add_column(
        "chunk_versions",
        sa.Column("headings", postgresql.ARRAY(sa.Text()), nullable=False),
        schema="corpus",
    )
    op.create_index(
        "ix_chunk_versions_document_ordinal",
        "chunk_versions",
        ["document_id", "ordinal"],
        schema="corpus",
    )
    op.drop_table("section_revisions", schema="corpus")


def downgrade() -> None:
    raise RuntimeError("0021 has no downgrade: chunks are re-cut per document")
```

`corpus_repository.py`: `_placement_row` ghi `document_id`, `ordinal`; `index_items` bỏ join `SectionRevisionTable`/`SectionTable`, join `DocumentTable` qua `ChunkVersionTable.document_id`, bỏ `kind`; purge và mọi truy vấn khác bỏ `section_revisions`. `qdrant_index.py`: `KEYWORD_PAYLOAD_FIELDS = ("release_ids", "document_id")`, `point_payload` trả `collection_id`, `release_ids`, `document_id`. `tests/corpus_memory.py`, `tests/corpus_rows.py`: cùng trường; `test_migrations.py` chạy tới head 0021 và kiểm bảng `section_revisions` không còn; `test_persistence_metadata.py` cập nhật danh sách bảng.

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `cd backend && uv run pytest tests/domain/corpus tests/infrastructure/test_corpus_repository.py tests/infrastructure/test_qdrant_index.py tests/infrastructure/test_qdrant_adapter.py tests/infrastructure/test_migrations.py tests/infrastructure/test_persistence_metadata.py -q`
Expected: PASS. Rồi `uv run pytest -q` toàn backend để thấy chính xác các test retrieval còn fail (Task 3 sửa).

- [ ] **Step 5: Commit**

```bash
git add backend/src backend/tests
git commit -m "feat(backend): chunk versions belong to documents; drop section revisions and hydrate columns (0021)"
```

---

### Task 3: Retrieval không hydrate, 5 chunk mỗi lượt, citation một chunk

**Files:**
- Modify: `backend/src/pharma_agent/domain/retrieval/models.py` (xoá `HydrateStrategy`, `Chunk`, `RetrievedItem`; `Hit`, `ChunkRecord`)
- Modify: `backend/src/pharma_agent/domain/retrieval/ports.py` (xoá `Hydrator`; `CorpusReader.section_chunks` thành `document_chunks`)
- Modify: `backend/src/pharma_agent/domain/retrieval/service.py`, `backend/src/pharma_agent/domain/retrieval/evidence.py`, `backend/src/pharma_agent/domain/agent/budget.py`, `backend/src/pharma_agent/domain/agent/run.py` (`record_search` payload), `backend/src/pharma_agent/domain/agent/citations.py`
- Modify: `backend/src/pharma_agent/infrastructure/retrieval/postgres_corpus.py` (xoá `PostgresHydrator`), `backend/src/pharma_agent/infrastructure/composition.py`, `backend/src/pharma_agent/infrastructure/settings.py` (`top_n = 5`, bỏ `hydrate_window`), `backend/src/pharma_agent/cli.py`
- Modify: `backend/src/pharma_agent/domain/conversation/models.py`, `backend/src/pharma_agent/application/conversation/citations.py`, `backend/src/pharma_agent/infrastructure/persistence/postgres/citation_rows.py`, `backend/src/pharma_agent/infrastructure/persistence/postgres/tables.py` (`MessageCitationTable`)
- Modify: `frontend/openapi.json`, `frontend/app/api/gen/**` (sinh lại), `frontend/app/features/chat/components/CitationSheet.tsx` và test `.browser.test.tsx`, `frontend/tests/chat/fixtures.ts`
- Test: `backend/tests/domain/test_evidence.py`, `test_retrieval_service.py`, `test_citations.py`, `tests/api/test_citations_api.py`, `tests/infrastructure/test_postgres_corpus.py`, `test_corpus_retrieval_integration.py`, `test_conversation_repository.py`, `tests/contract/test_ui_stream_fixtures.py`, `tests/domain/factories.py`, `tests/fakes.py`, `tests/citations.py`, `tests/application/test_chat_graph.py`, `tests/domain/test_agent_run.py`

**Interfaces:**
- Produces: `Hit(chunk_version_id, release_id, collection_id, document_key, ordinal, section_keys: list[str], headings: list[str], source, title, start_page, end_page, context_header, chunk_text, embedding_text, colloquial_mapping, term_annotations, fusion_score, rerank_score, matched_queries)` với property `section -> "; ".join(headings)`; `SearchResult.items: list[Hit]`; `Evidence(ref, hit, superseded)` với `text()`; `EvidenceSet.merge(hits: list[Hit])`, `pack(max_chars) -> list[Evidence]`; `CorpusReader.document_chunks(release_id, document_id, ordinals: Sequence[int]) -> list[ChunkRecord]`; `Citation(index, chunk_version_id, release_id, source, title, section, start_page, end_page, snippet)`; `CitationBlock(citation, text, is_current)`; `CitationDetail(index, source, document_title, section, start_page, end_page, is_current, text)`; `BudgetLimits.max_evidence_chars = 30_000`; `RerankSettings.top_n = 5`; log search payload `"evidence": [{"document": key, "ordinal": n, "sections": [...]}]`.

- [ ] **Step 1: Viết test fail cho evidence và payload**

`backend/tests/domain/test_evidence.py` (thay các test về `applied_strategy`/`_window`):

```python
def test_evidence_text_is_the_hit_text() -> None:
    hit = make_hit("c1", text="## Liều dùng\n\n500 mg")
    evidence = Evidence(ref="E1", hit=hit)
    assert evidence.text() == "## Liều dùng\n\n500 mg"


def test_pack_drops_whole_chunks_never_truncates() -> None:
    hits = [make_hit(f"c{i}", rerank=1.0 - i / 10, text="a" * 1000) for i in range(5)]
    evidence = EvidenceSet()
    evidence.merge(hits)
    packed = evidence.pack(max_chars=2500)
    assert [e.hit.chunk_version_id for e in packed] == [
        h.chunk_version_id for h in hits[:2]
    ]
    assert all(len(e.text()) == 1000 for e in packed)
```

`backend/tests/domain/test_agent_run.py`, sửa test `test_each_search_logs_the_evidence_it_leaves_active` (Task 7b đã thêm) thành:

```python
run.record_search(Q1, SearchResult(items=[hit_a, hit_b]), now=NOW)
search = run.actions.entries[-1]
assert search.payload["evidence"] == [
    {"document": "drug:a", "ordinal": 2, "sections": ["drug:a:lieu-dung"]},
    {
        "document": "drug:a",
        "ordinal": 1,
        "sections": ["drug:a:chi-dinh", "drug:a:thanh-phan"],
    },
]
```

với `hit_a = make_hit("c1", document_key="drug:a", ordinal=2, section_keys=["drug:a:lieu-dung"])` và `hit_b` tương tự; `make_hit` trong `tests/domain/factories.py` nhận `document_key`, `ordinal`, `section_keys`, `headings`.

`backend/tests/api/test_citations_api.py`: body có `text` và không có `chunks`, `strategy`:

```python
    assert body["text"] == "## Liều dùng\n\nparacetamol 500 mg"
    assert "chunks" not in body and "strategy" not in body
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && uv run pytest tests/domain/test_evidence.py tests/domain/test_agent_run.py tests/api/test_citations_api.py -q`
Expected: FAIL (`Evidence` còn đòi `applied_strategy`; payload cũ; body có `chunks`).

- [ ] **Step 3: Gỡ hydrate khỏi domain, hạ tầng và API**

`retrieval/models.py`: xoá `HydrateStrategy`, `Chunk`, `RetrievedItem`; `Hit` và `ChunkRecord` bỏ `section_key`, `section_revision_id`, `hydrate_strategy`, `section`, `kind`, `table_key`, thêm `section_keys: list[str]`, `headings: list[str]`, property:

```python
    @property
    def section(self) -> str:
        return "; ".join(h for h in self.headings if h)
```

`ports.py`: xoá `Hydrator`; `CorpusReader.section_chunks` thay bằng `async def document_chunks(self, release_id: UUID, document_id: UUID, ordinals: Sequence[int]) -> list[ChunkRecord]` (docstring: "Chunks of one document in one release, by ordinal; for the agent's read tool.").

`service.py`: bỏ tham số `hydrator`; `SearchResult.items: list[Hit]`; sau rerank trả `items=ranked` (xoá vòng hydrate). `evidence.py`:

```python
class Evidence(BaseModel):
    ref: str
    hit: Hit
    superseded: bool = False

    @property
    def score(self) -> float:
        return self.hit.score

    def text(self) -> str:
        return self.hit.chunk_text

    def char_count(self) -> int:
        return len(self.hit.chunk_text)


class EvidenceSet(BaseModel):
    ...
    def merge(self, retrieved: list[Hit]) -> list[Evidence]:  # thân giữ nguyên, item là Hit
    def pack(self, max_chars: int) -> list[Evidence]:
        """Whole chunks by score until max_chars is spent; never truncates a chunk."""
        packed: list[Evidence] = []
        remaining = max_chars
        for evidence in self.active():
            if evidence.char_count() <= remaining:
                packed.append(evidence)
                remaining -= evidence.char_count()
        return packed
```

Xoá `_window`, `_fit`, `ordered_chunks`, `text_chunk_version_ids`. `budget.py`: `max_evidence_chars: int = 30_000`. `run.py` `record_search` payload: `"evidence": [{"document": e.hit.document_key, "ordinal": e.hit.ordinal, "sections": list(e.hit.section_keys)} for e in active]`. `agent/citations.py` `citations_from`: bỏ `strategy`, `block_chunk_version_ids`. `postgres_corpus.py`: `_record` đọc `document` qua `ReleaseChunkTable.document_id`, điền `section_keys=list(chunk.section_keys)`, `headings=list(chunk.headings)`; `load_chunks` join `DocumentTable.id == ReleaseChunkTable.document_id`; thay `section_chunks` bằng `document_chunks` (where `release_id`, `document_id`, `ordinal.in_(ordinals)`, order by ordinal, trả `ChunkRecord`); xoá `PostgresHydrator`. `composition.py`: bỏ `PostgresHydrator` và `hydrate_window`; `settings.py`: `top_n: int = 5`, xoá `hydrate_window`; `cli.py` probe bỏ `hydrate_strategy`.

Citation: `conversation/models.py` `Citation` bỏ `strategy`, `block_chunk_version_ids`; `CitationBlock(citation, text: str, is_current: bool)`, xoá `CitedChunk`. `tables.py` `MessageCitationTable` bỏ check constraint `strategy`, cột `strategy`, `block_chunk_version_ids`. `citation_rows.py` theo đó, `load_citations` và hàm đọc block trả `text=chunk.chunk_text`. `application/conversation/citations.py`:

```python
class CitationDetail(BaseModel):
    index: int
    source: str
    document_title: str
    section: str
    start_page: int | None
    end_page: int | None
    is_current: bool
    text: str

    @classmethod
    def of(cls, block: CitationBlock) -> "CitationDetail":
        c = block.citation
        return cls(
            index=c.index,
            source=c.source,
            document_title=c.title,
            section=c.section,
            start_page=c.start_page,
            end_page=c.end_page,
            is_current=block.is_current,
            text=block.text,
        )
```

Frontend: `cd frontend && npm run api:openapi && npm run api:generate`; `CitationSheet.tsx` bỏ `STRATEGY_KEYS`, badge strategy và vòng `detail.chunks.map`, hiện một khối `<p className="whitespace-pre-wrap">{detail.text}</p>` với cùng class nền đang dùng cho chunk matched; xoá khoá i18n `strategy.*`; cập nhật `CitationSheet.browser.test.tsx` và `tests/chat/fixtures.ts`; `npm run typecheck && npm test`.

Backend tests: `factories.py` (`make_hit`, `make_item` thành `make_hit`, `search_result` trả `SearchResult(items=[make_hit(...)])`), `fakes.py` và `citations.py` bỏ hydrator/strategy, `test_retrieval_service.py` bỏ các test hydrate, `test_postgres_corpus.py` thay test `section_chunks` bằng `document_chunks`, `test_corpus_retrieval_integration.py`, `test_conversation_repository.py`, `test_ui_stream_fixtures.py` (fixture JSON bỏ `strategy`), `test_chat_graph.py`.

- [ ] **Step 4: Chạy gate backend và frontend, xác nhận pass**

Run: `cd backend && uv run ruff check src tests && uv run ruff format src tests && uv run pyrefly check --min-severity warn && uv run pytest -q && cd ../frontend && npm run api:check && npm run typecheck && npm test`
Expected: PASS; `grep -rn "hydrat\|Hydrat\|section_revision\|block_chunk_version_ids" backend/src frontend/app` trả về rỗng.

- [ ] **Step 5: Commit**

```bash
git add backend frontend/openapi.json frontend/app frontend/tests
git commit -m "feat(backend): retrieval reads chunks as is; five chunks per round; one-chunk citations"
```

---

### Task 4: pharma-lab đọc chunk theo tài liệu

**Files:**
- Modify: `pharma-lab/src/pharma_lab/bundle/chunks.py`, `pharma-lab/src/pharma_lab/bundle/evaluation_chunks.py`, `pharma-lab/src/pharma_lab/bundle/embed.py`, `pharma-lab/src/pharma_lab/evaluation/backend_retrieval.py` (payload ứng viên), `pharma-lab/src/pharma_lab/e2e/corpus_text.py` (`chunk_texts`), `pharma-lab/src/pharma_lab/e2e/sampling.py` (`_focus`)
- Test: `pharma-lab/tests/bundle/test_evaluation_chunks.py`, `pharma-lab/tests/bundle/test_embed.py`, `pharma-lab/tests/evaluation/test_backend_retrieval.py`, `pharma-lab/tests/e2e/test_sampling.py`, `pharma-lab/tests/e2e/test_golden.py` (`chunk_texts`)

**Interfaces:**
- Consumes: `chunk_document`, `ChunkDraft` (Task 1); `Hit.section_keys` (Task 3).
- Produces: `gold_chunk_label(document_key: str, ordinal: int) -> str`; `iter_document_chunks(bundle) -> Iterator[DocumentChunks(document, sections: list[SectionRecord], drafts: list[ChunkDraft])]`; hàng chunk đánh giá `{"chunk_id", "document_id", "ordinal", "section_ids": [...], "headings": [...], "title", "source", "content_type", "context_header", "chunk_text", "embedding_text", "has_table": bool, "has_list": bool, "colloquial_mapping", "term_annotations"}`; payload ứng viên retrieval `{"chunk_id", "document_id", "section_ids": [...]}`; `chunk_texts(bundle, section_ids) -> dict[label, text]` trả các chunk chứa mục.

- [ ] **Step 1: Viết test fail**

`pharma-lab/tests/bundle/test_evaluation_chunks.py`:

```python
def test_rows_name_the_document_and_every_section_in_the_chunk(bundle_small) -> None:
    rows = evaluation_chunk_rows(bundle_small)
    row = next(r for r in rows if len(r["section_ids"]) > 1)
    assert row["chunk_id"] == f"{row['document_id']}:chunk-{row['ordinal']:03d}"
    assert all(s.startswith(row["document_id"]) for s in row["section_ids"])
    assert set(rows[0]) >= {
        "has_table",
        "has_list",
        "headings",
        "context_header",
        "embedding_text",
    }
    assert "hydrate_strategy" not in rows[0] and "chunk_role" not in rows[0]
```

(`bundle_small` là bundle export từ `tests/fixtures/rag_final_small` như các test bundle khác đang làm.)

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd pharma-lab && uv run pytest tests/bundle/test_evaluation_chunks.py -q`
Expected: FAIL (`KeyError: 'section_ids'`).

- [ ] **Step 3: Sửa chunk iteration, hàng đánh giá, payload**

`bundle/chunks.py`:

```python
@dataclass(frozen=True)
class DocumentChunks:
    document: DocumentRecord
    sections: list[SectionRecord]
    drafts: list[ChunkDraft]


def gold_chunk_label(document_key: str, ordinal: int) -> str:
    """Position label used by evaluation gold sets: the document and the chunk's ordinal."""
    return f"{document_key}:chunk-{ordinal:03d}"


def iter_document_chunks(bundle: KnowledgeBundle) -> Iterator[DocumentChunks]:
    by_document: dict[str, list[SectionRecord]] = defaultdict(list)
    for section in bundle.sections:
        by_document[section.document_key].append(section)
    for document in bundle.documents:
        sections = by_document.get(document.key, [])
        yield DocumentChunks(
            document,
            sections,
            chunk_document(
                document, sections, bundle.glossary, bundle.colloquial_mappings
            ),
        )
```

`evaluation_chunks.py`: bỏ `hydrate_strategy_for`, `CHUNK_ROLES`; mỗi draft một hàng với các trường ở Interfaces; `has_table`/`has_list` tính từ `block.kind` của các section trong `draft.section_keys` (`BlockKind.TABLE`; `LIST` hoặc `INDEX_ENTRIES`). `embed.py`: id dùng `gold_chunk_label(draft.document_key, draft.ordinal)`. `backend_retrieval.py` payload: `{"chunk_id": label, "document_id": hit.document_key, "section_ids": list(hit.section_keys)}` (label từ `hit.document_key`, `hit.ordinal`). `corpus_text.chunk_texts`: duyệt `iter_document_chunks`, giữ draft nào có `set(draft.section_keys) & wanted`. `sampling._focus` không đổi logic (nhận label mới).

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `cd pharma-lab && uv run pytest tests/bundle tests/e2e/test_sampling.py tests/e2e/test_golden.py tests/evaluation/test_backend_retrieval.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pharma-lab/src pharma-lab/tests
git commit -m "feat(pharma-lab): evaluation chunks and labels follow the document chunker"
```

---

### Task 5: Benchmark theo section, nhóm `structured`, hit theo mục trong chunk

**Files:**
- Modify: `pharma-lab/src/pharma_lab/evaluation/section_eval_schema.py` (quota `structured`, `EVAL_HEADER`, xoá `retrieval_granularity_from_hydrate_strategy`)
- Modify: `pharma-lab/src/pharma_lab/evaluation/build_section_retrieval_eval.py` (xoá `expected_chunk_*`, `retrieval_granularity`, `is_chunk_risk`, `retrieval_granularity_for_row`; `chunk_risk_candidates` thành `structured_candidates`)
- Modify: `pharma-lab/src/pharma_lab/evaluation/retrieval_metrics.py` (`is_hit`, `satisfied_units`, `ranking_scores`, `score_ranked_payloads`)
- Modify: `pharma-lab/src/pharma_lab/evaluation/relevance_judgments.py` (`_accepted_leaflet_chunks` đọc `section_ids`, `ordinal`)
- Modify: `pharma-lab/src/pharma_lab/e2e/one_round.py` (`coverage` dùng `satisfied_units`; mặc định `top_k=5` ở CLI)
- Test: `pharma-lab/tests/evaluation/test_retrieval_metrics.py`, `test_build_section_retrieval_eval.py`, `test_relevance_judgments.py`, `test_metrics_service.py`, `pharma-lab/tests/e2e/test_one_round.py`

**Interfaces:**
- Consumes: hàng chunk đánh giá và payload `section_ids` (Task 4).
- Produces: `is_hit(payload, expected, accepted_chunk_ids) -> bool` (payload có `section_ids`); `satisfied_units(payload, query_row, judged) -> set[str]`; hàng benchmark không còn `expected_chunk_id`, `expected_chunk_index`, `expected_chunk_role`, `retrieval_granularity`; `EVAL_GROUP_QUOTAS["structured"] = 1000`.

- [ ] **Step 1: Viết test fail cho metric**

`pharma-lab/tests/evaluation/test_retrieval_metrics.py` thêm:

```python
def _payload(*sections: str) -> dict:
    return {
        "chunk_id": "drug:a:chunk-001",
        "document_id": "drug:a",
        "section_ids": list(sections),
    }


def test_hit_when_any_section_of_the_chunk_is_gold() -> None:
    row = {
        "query_id": "q",
        "answer_mode": "single",
        "expected_section_id": "drug:a:lieu-dung",
        "expected_section_ids": ["drug:a:lieu-dung"],
    }
    assert is_hit(_payload("drug:a:chi-dinh", "drug:a:lieu-dung"), row)
    assert not is_hit(_payload("drug:a:chi-dinh"), row)


def test_one_chunk_satisfies_several_units() -> None:
    gold = ["drug:a:chi-dinh", "drug:a:lieu-dung"]
    row = {
        "query_id": "q",
        "answer_mode": "multi_required",
        "expected_section_id": gold[0],
        "expected_section_ids": gold,
    }
    assert satisfied_units(_payload(*gold), row, {}) == set(gold)
    scores = ranking_scores([_payload(*gold)], row, judged={})
    assert scores["ndcg@10"] == 1.0 and scores["mrr@10"] == 1.0


def test_accepted_chunk_counts_as_hit() -> None:
    row = {
        "query_id": "q",
        "answer_mode": "single",
        "expected_section_id": "drug:a:lieu-dung",
        "expected_section_ids": ["drug:a:lieu-dung"],
    }
    judged = {"drug:a:lieu-dung": frozenset({"leaflet:t:b:chunk-002"})}
    payload = {
        "chunk_id": "leaflet:t:b:chunk-002",
        "document_id": "leaflet:t:b",
        "section_ids": ["leaflet:t:b:03-cach-dung"],
    }
    assert satisfied_units(payload, row, judged) == {"answer"}
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd pharma-lab && uv run pytest tests/evaluation/test_retrieval_metrics.py -q`
Expected: FAIL (`satisfied_units` chưa có; `is_hit` đọc `section_id`).

- [ ] **Step 3: Viết metric mới và dọn builder**

`retrieval_metrics.py`: xoá `expected_chunk_ids`, `_chunk_id` dùng `payload["chunk_id"]`; thay `is_hit` và `satisfied_unit`:

```python
def _sections(payload: Mapping[str, object]) -> set[str]:
    raw = payload.get("section_ids")
    return {str(s) for s in raw} if isinstance(raw, list) else set()


def is_hit(
    payload: dict, expected: dict, accepted_chunk_ids: frozenset[str] = frozenset()
) -> bool:
    """A chunk answers the row when it holds a gold section or a judged accepted chunk."""
    if accepted_chunk_ids and _chunk_id(payload) in accepted_chunk_ids:
        return True
    return bool(_sections(payload) & set(expected_section_ids(expected)))


def satisfied_units(
    payload: dict, query_row: dict, judged: Mapping[str, frozenset[str]]
) -> set[str]:
    """Every evidence unit a retrieved chunk satisfies (a chunk may hold several sections)."""
    units = evidence_units(query_row)
    if units == ("answer",):
        accepted = frozenset().union(*judged.values()) if judged else frozenset()
        return {"answer"} if is_hit(payload, query_row, accepted) else set()
    chunk = _chunk_id(payload)
    held = _sections(payload)
    return {u for u in units if u in held or chunk in judged.get(u, ())}
```

`ranking_scores`, `score_ranked_payloads`: bỏ tham số `window_size`, dùng `satisfied_units` (gain cho mọi unit mới của chunk ở cùng hạng); `multi_section_recall@k` đếm unit thoả bởi bất kỳ chunk trong top k. `metrics_service.py` bỏ `window_size` khỏi request và identity.

`section_eval_schema.py`: `"structured": 1000` thay `"chunk_risk"`; `EVAL_HEADER` bỏ bốn cột chunk; xoá `retrieval_granularity_from_hydrate_strategy`. `build_section_retrieval_eval.py`: xoá bốn trường khỏi `make_row` và mọi lời gọi; `is_chunk_risk(chunk)` thành `is_structured(chunk) -> bool: return chunk["has_table"] or chunk["has_list"]`; `chunk_risk_candidates` thành `structured_candidates` (section gold = mục chứa bảng/danh sách; câu hỏi theo intent của mục như hiện nay); nhãn nhóm `"structured"`; các hàm `expected_role`/`chunk_role` chỉ còn dùng để chọn câu hỏi, bỏ khỏi output. `relevance_judgments.py` `_accepted_leaflet_chunks`: gom theo `document_id` (hàng có `document_id`), sắp theo `ordinal`, intent của chunk đọc từ heading trong `chunk_text` (`heading_intent` theo từng dòng `## `), chấp nhận `chunk_id`. `one_round.py` `coverage`: `found = set().union(*(satisfied_units(dict(p), dict(row), judged) for p in ranked[:top_k]))`; CLI `--top-k` mặc định 5 ở `hard-candidates` và `trim`.

Tests: cập nhật `test_build_section_retrieval_eval.py` (fixture hàng chunk có `section_ids`, `has_table`), `test_relevance_judgments.py`, `test_metrics_service.py`, `test_one_round.py` (payload có `section_ids`, top_k 5).

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `cd pharma-lab && uv run pytest tests/evaluation tests/e2e/test_one_round.py -q`
Expected: PASS; `grep -rn "chunk_risk\|retrieval_granularity\|expected_chunk\|chunk_window\|chunk_exact\|hydrate" pharma-lab/src` rỗng trừ pipeline rag-final (Task 7).

- [ ] **Step 5: Commit**

```bash
git add pharma-lab/src pharma-lab/tests
git commit -m "feat(pharma-lab): benchmark scores sections inside chunks; structured group replaces chunk_risk"
```

---

### Task 6: Golden v3 và báo cáo e2e theo section

**Files:**
- Modify: `pharma-lab/src/pharma_lab/e2e/golden.py` (`SCHEMA = "e2e-golden-v3"`, `EVAL_GROUPS` với `structured`, bỏ `gold_chunk_ids`), `sampling.py` (strata), `executor.py` (`CitedSection.chunk_id`, `retrieved_chunk_ids`, `rounds`), `records.py` (`rounds` docstring: section keys), `report.py` (`_round_coverage` trên section key), `cli/commands/e2e.py`
- Modify (dữ liệu): `pharma-lab/data/evaluation/e2e/authoring/*.jsonl` (`"eval_group": "chunk_risk"` thành `"structured"`, xoá trường `gold_chunk_ids`)
- Test: `pharma-lab/tests/e2e/test_golden.py`, `test_report.py`, `test_executor.py`, `test_sampling.py`, `tests/e2e/factories.py`

**Interfaces:**
- Consumes: payload search `{"document", "ordinal", "sections"}` (Task 3), `gold_chunk_label` (Task 4).
- Produces: `GoldenItem` không có `gold_chunk_ids`; `AnswerRecord.rounds: list[list[str]]` là section key còn hiệu lực sau mỗi vòng; `CitedSection(index, chunk_version_id, chunk_id, section_ids: list[str])`; `AnswerRecord.retrieved_chunk_ids` là nhãn `<document>:chunk-NNN`.

- [ ] **Step 1: Viết test fail**

`tests/e2e/test_golden.py`: `answerable()` không đặt `gold_chunk_ids`; thêm

```python
def test_golden_schema_is_v3_without_chunk_ids() -> None:
    assert SCHEMA == "e2e-golden-v3"
    with pytest.raises(ValidationError):
        GoldenItem.model_validate(
            {**answerable().model_dump(mode="json"), "gold_chunk_ids": ["x"]}
        )
```

`tests/e2e/test_report.py`: `_loop_view(rounds=[["drug:x:lieu-dung"], ["drug:x:lieu-dung", "drug:x:chi-dinh"]], gold)` và bỏ `test_judged_chunks_count_as_gold_found`. `tests/e2e/test_executor.py`: run giả có action SEARCH payload `{"evidence": [{"document": "drug:a", "ordinal": 1, "sections": ["drug:a:chi-dinh", "drug:a:lieu-dung"]}]}`, kiểm `record.rounds == [["drug:a:chi-dinh", "drug:a:lieu-dung"]]` và `record.retrieved_chunk_ids == ["drug:a:chunk-001"]`.

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd pharma-lab && uv run pytest tests/e2e -q`
Expected: FAIL (schema còn v2, `gold_chunk_ids` còn nhận).

- [ ] **Step 3: Sửa golden, executor, report, dữ liệu**

`golden.py`: `SCHEMA = "e2e-golden-v3"`, `EVAL_GROUPS = ("formulary", "leaflet", "structured", "leaflet_short", "noisy", "multi_intent")`, xoá `gold_chunk_ids` và nhánh kiểm tra nó. `executor.py`:

```python
citations.append(
    CitedSection(
        index=citation.index,
        chunk_version_id=str(citation.chunk_version_id),
        chunk_id=None
        if hit is None
        else gold_chunk_label(hit.document_key, hit.ordinal),
        section_ids=[] if hit is None else list(hit.section_keys),
    )
)
...
retrieved_chunk_ids = (
    [
        gold_chunk_label(e.hit.document_key, e.hit.ordinal)
        for e in run.evidence.active()
    ],
)
rounds = (
    [
        sorted({s for item in action.payload["evidence"] for s in item["sections"]})
        for action in entries
        if action.kind is ActionKind.SEARCH
    ],
)
```

`report.py` `_round_coverage(view, sections)`: `found = sum(1 for s in view.item.gold_section_ids if s in set(sections))`. Dữ liệu authoring: `sed -i 's/"eval_group": "chunk_risk"/"eval_group": "structured"/' pharma-lab/data/evaluation/e2e/authoring/*.jsonl` rồi một script python xoá khoá `gold_chunk_ids` khỏi từng dòng JSON (ghi lại với `ensure_ascii=False`).

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `cd pharma-lab && uv run pytest tests/e2e -q && for f in data/evaluation/e2e/authoring/*.authored.jsonl; do uv run pharma-lab e2e golden check "$f" | tail -1; done`
Expected: PASS; mọi batch `items=N` không lỗi (golden check không cần bundle mới vì quote nằm trong section).

- [ ] **Step 5: Commit**

```bash
git add pharma-lab/src pharma-lab/tests pharma-lab/data/evaluation/e2e/authoring
git commit -m "feat(pharma-lab): golden v3 keeps gold by section; loop coverage by section keys"
```

---

### Task 7: rag-final chỉ còn section và block; bundle không có chế độ index-only

**Files:**
- Modify: `pharma-lab/src/pharma_lab/corpus/processing/preprocess_rag_corpus.py` (xoá `ChunkRecord`, `chunk_sections`, ghi `chunks.jsonl`), `corpus/canonical/build_canonical_rag.py` (xoá `hydrate_strategy_for_section`, `chunk_role_for_section`, `build_final_chunk_records`, `annotate_chunks_for_hydration`, trường `hydrate_strategy`, `section_char_count`, manifest `rag_chunks`), `corpus/crawling/integrate_leaflets.py` (xoá `chunk_text`, chunk records, `hydrate_strategy`, `section_char_count`; `integrate_drug_file` trả `sections`), `corpus/validation/validate_final_rag.py` (xoá `validate_hydration_metadata`, `validate_chunk_source_blocks`, `validate_brand_index_chunks`, `audit_tables_and_chunks` phần chunk, đọc `chunks.jsonl`), `orchestration/build_corpus.py` (bỏ đường dẫn chunks), `bundle/export.py` (bỏ `RetrievalMode`), `backend/src/pharma_agent/domain/corpus/bundle.py` (xoá `RetrievalMode`, trường `retrieval`), `pharma-lab/pyproject.toml` (`version = "0.4.0"`), `pharma-lab/data/README.md`, `pharma-lab/docs/guides/downstream.md`
- Delete: `pharma-lab/tests/fixtures/rag_final_small/chunks.jsonl`; sửa `sections.jsonl` của fixture (bỏ `hydrate_strategy`, `section_char_count`)
- Test: `pharma-lab/tests/corpus/**`, `tests/bundle/test_export.py`, `tests/test_project_identity.py`, `backend/tests/domain/corpus/test_bundle_models.py`

- [ ] **Step 1: Viết test fail**

`pharma-lab/tests/corpus/test_integrate_leaflets.py`: `integrate_drug_file(...)` trả về `sections` (một giá trị), test `test_integrate_drug_file_emits_one_section_per_heading` bỏ phần `chunks`; thêm `assert "hydrate_strategy" not in first and "section_char_count" not in first`. `backend/tests/domain/corpus/test_bundle_models.py`: `SectionRecord` từ chối khoá `retrieval` (`extra="forbid"` đã có).

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd pharma-lab && uv run pytest tests/corpus/test_integrate_leaflets.py -q`
Expected: FAIL (hàm còn trả tuple, record còn `hydrate_strategy`).

- [ ] **Step 3: Gỡ chunk và hydrate khỏi pipeline**

Xoá các hàm liệt kê ở Files; `build_canonical_rag` ghi `sections.jsonl`, `blocks.jsonl`, manifest không có `rag_chunks`; `validate_final_rag` chỉ validate section và block; `build_corpus.py` bỏ mọi `chunks_path`. `bundle.py` xoá `RetrievalMode` và trường `retrieval`; `export.py` bỏ import và tham số. `pyproject.toml` version `0.4.0` rồi `uv lock`. Fixture `sections.jsonl` bỏ hai trường. `data/README.md` bỏ dòng `chunks.jsonl` của rag-final; `downstream.md` bỏ mục 7 về hydrate, thay bằng một câu "Chunk do backend cắt khi import; bundle chỉ chứa section và block".

- [ ] **Step 4: Chạy gate hai package, xác nhận pass**

Run: `cd pharma-lab && uv run ruff check src tests && uv run ruff format src tests && uv run pyrefly check --min-severity warn && uv run pytest -q && cd ../backend && uv run pytest -q`
Expected: PASS; `grep -rn "hydrat\|section_char_count\|RetrievalMode\|chunks.jsonl" pharma-lab/src backend/src` rỗng.

- [ ] **Step 5: Commit**

```bash
git add pharma-lab backend/src backend/tests uv.lock
git commit -m "refactor(pharma-lab): rag-final keeps sections and blocks only; pipeline 0.4.0"
```

---

### Task 8: Ngân sách evidence 60.000 ký tự, pack bỏ từ đáy, search ghi cỡ evidence

Spec §3.0c sửa ngày 2026-10-15 (commit b7c0d27): `max_evidence_chars = 60000`; `pack` xếp theo điểm rerank xuyên mọi vòng và bỏ nguyên chunk điểm thấp nhất khi vượt; mỗi vòng ghi số chunk và cỡ evidence. ReAct chỉ có một công cụ `search_corpus`, nên `CorpusReader.document_chunks` không còn người dùng và bị xoá.

**Files:**
- Modify: `backend/src/pharma_agent/domain/agent/budget.py` (`max_evidence_chars: int = 60_000`)
- Modify: `backend/src/pharma_agent/domain/retrieval/evidence.py` (`pack`)
- Modify: `backend/src/pharma_agent/domain/agent/run.py` (`record_search` payload thêm `"evidence_chars"`)
- Modify: `backend/src/pharma_agent/domain/retrieval/ports.py`, `backend/src/pharma_agent/infrastructure/retrieval/postgres_corpus.py` (xoá `document_chunks`), cùng test của nó
- Test: `backend/tests/domain/retrieval/test_evidence.py`, `backend/tests/domain/agent/test_run.py`

**Interfaces:**
- Produces: payload SEARCH có `"evidence_chars": int` = tổng ký tự của `self.evidence.pack(limits.max_evidence_chars)` sau vòng đó; Task 9 đọc.

- [ ] **Step 1: Test hỏng**

```python
def test_pack_drops_whole_chunks_from_the_lowest_score() -> None:
    evidence = EvidenceSet()
    evidence.merge(
        [
            _hit(score=0.9, chars=40),
            _hit(score=0.8, chars=40),
            _hit(score=0.1, chars=10),
        ]
    )

    packed = evidence.pack(85)

    # The 0.8 chunk does not fit next to the 0.9 one; everything ranked below it goes too.
    assert [e.score for e in packed] == [0.9]


def test_default_evidence_budget_is_sixty_thousand_chars() -> None:
    assert RunLimits().max_evidence_chars == 60_000
```

và trong test của `record_search`: `payload["evidence_chars"] == sum(len(h.chunk_text) for h in hits)`.

- [ ] **Step 2: Chạy, thấy hỏng** — `cd backend && uv run pytest tests/domain -q`. Expected: 3 test mới FAIL.

- [ ] **Step 3: Cài đặt**

```python
    def pack(self, max_chars: int) -> list[Evidence]:
        """Whole chunks by score; once one does not fit, it and every lower one are dropped."""
        packed: list[Evidence] = []
        remaining = max_chars
        for evidence in self.active():
            if evidence.char_count() > remaining:
                break
            packed.append(evidence)
            remaining -= evidence.char_count()
        return packed
```

`record_search` thêm `"evidence_chars": sum(e.char_count() for e in self.evidence.pack(self.limits.max_evidence_chars))`. Xoá `document_chunks` khỏi port, adapter và test.

- [ ] **Step 4: Chạy lại** — `cd backend && uv run pytest -q`. Expected: pass hết.

- [ ] **Step 5: Commit** — `git commit -m "feat(backend): 60k-char evidence budget, pack drops from the lowest score"`

---

### Task 9: pharma-lab theo spec mới: `section_coverage`, vòng ghi cỡ evidence, nDCG@5 và MRR@5

**Files:**
- Modify: `pharma-lab/src/pharma_lab/evaluation/section_eval_schema.py`, `build_section_retrieval_eval.py` (`chunk_coverage` → `section_coverage`), tài liệu golden authoring
- Modify: `pharma-lab/src/pharma_lab/e2e/records.py` (`RoundRecord`), `executor.py`, `report.py`
- Modify: `pharma-lab/src/pharma_lab/evaluation/retrieval_metrics.py` (nDCG và MRR ở 5 và 10)
- Test: `tests/evaluation/test_retrieval_metrics.py`, `tests/e2e/test_executor.py`, `tests/e2e/test_report.py`, test schema

**Interfaces:**
- Consumes: payload SEARCH `"evidence"` và `"evidence_chars"` (Task 8).
- Produces: `RoundRecord(sections: list[str], chunks: int, evidence_chars: int)`; `AnswerRecord.rounds: list[RoundRecord]`; điểm `ndcg@5`, `mrr@5`, `ndcg@10`, `mrr@10`.

- [ ] **Step 1: Test hỏng**

```python
def test_ranking_scores_at_5_and_10() -> None:
    payloads = _ranked(*["x:z"] * 5, "drug:a:lieu")
    scores = score_ranked_payloads(payloads, _section_row(), top_k=10)
    assert scores["ndcg@5"] == 0.0 and scores["mrr@5"] == 0.0
    assert scores["mrr@10"] == pytest.approx(1 / 6)
```

`test_executor`: `record.rounds == [RoundRecord(sections=sorted([SECTION, "other"]), chunks=2, evidence_chars=...)]`. Test schema: `"section_coverage" in QUERY_FORMS and "chunk_coverage" not in QUERY_FORMS`.

- [ ] **Step 2: Chạy, thấy hỏng** — `cd pharma-lab && uv run pytest tests/evaluation tests/e2e -q`.

- [ ] **Step 3: Cài đặt** — `RANKING_KS = (5, 10)`; `score_ranked_payloads` gọi `ranking_scores` cho mỗi k ≤ top_k. `report._coverage_after` đọc `rounds[index].sections`; thêm metric `evidence_chars_final`. Đổi tên query_form ở schema, builder và docs.

- [ ] **Step 4: Chạy lại** — `cd pharma-lab && uv run pytest -q`. Expected: pass hết.

- [ ] **Step 5: Commit** — `git commit -m "feat(pharma-lab): section_coverage, round evidence size, nDCG and MRR at 5"`

---

### Task 10: Dựng lại dữ liệu và đo chunk

**Files:**
- Dữ liệu: `pharma-lab/data/corpus/rag-final`, `pharma-lab/data/corpus/formulary` (manifest commit), `pharma-lab/data/evaluation/gold/*` (manifest commit), `pharma-lab/data/evaluation/e2e/golden_e2e.manifest.json`
- Ghi chú: `docs/research/paper-v2/07-dataset-review.md` thêm mục "Chunk v2 (2026-10-15)" với số đo

- [ ] **Step 1: Build corpus, bundle, benchmark, golden (tmux)**

```bash
cd pharma-lab
uv run pharma-lab build
uv run pharma-lab validate
uv run pharma-lab bundle export --output data/corpus/formulary --force
uv run pharma-lab evaluation build --bundle data/corpus/formulary
uv run pharma-lab e2e golden build
```

Expected: `status=complete` ở mỗi lệnh; benchmark 10.000 câu với `structured` 1.000, không còn query_form `chunk_coverage`; golden 500 (270/150/50/10/10/10).

- [ ] **Step 2: Kiểm tra dữ liệu**

Chạy đoạn Python kiểm tra: 0 câu có "(phần", 0 trùng text, 0 gold ngoài bundle (như kiểm tra ngày 2026-10-15), cộng: mỗi `expected_section_id` của benchmark nằm trong `section_ids` của đúng một chunk đánh giá.

- [ ] **Step 3: Đo token bằng tokenizer Qwen3 (docker `ghcr.io/ggml-org/llama.cpp:server-b10920`, model `qwen3-embedding-0.6b-q8_0.gguf`, endpoint `/tokenize`)**

Ghi vào `07-dataset-review.md`: số chunk, mean/p50/p90/p99/max token của `chunk_text` và `embedding_text`, số chunk dưới 64 token, số chunk nhiều mục. Điều kiện đạt: max token của `embedding_text` dưới 4.096 (slot embed, spec §3.0c, phương án A ngày 2026-10-15); mean `chunk_text` trong khoảng 900 đến 1.150 token. Nếu max vượt 4.096, giảm `MAX_CHUNK_CHARS` (Task 1) và chạy lại từ Step 1; nếu mean lệch khỏi khoảng, chỉnh `TARGET_CHUNK_CHARS` tương ứng và ghi giá trị đã chọn vào spec §3.0c.

- [ ] **Step 4: Commit**

```bash
git add pharma-lab/data/corpus/formulary/manifest.json pharma-lab/data/evaluation/gold/*.manifest.json pharma-lab/data/evaluation/e2e/golden_e2e.manifest.json docs/research/paper-v2/07-dataset-review.md docs/superpowers/specs/2026-10-14-paper-v2-design.md
git commit -m "data: corpus, benchmark and golden rebuilt on reading-sized chunks"
```

---

### Task 11: Tài liệu và plan pha D

**Files:**
- Modify: `pharma-lab/docs/guides/evaluation.md` (§1 dữ liệu: chunk theo tài liệu, nhãn, nhóm `structured`), `e2e-evaluation.md`, `e2e-golden-authoring.md` (top 5, không `gold_chunk_ids`), `cli-reference.md` (`--top-k 5`), `backend/README.md` (mục retrieval: không hydrate, `rerank.top_n = 5`), `README.md` gốc nếu nhắc hydrate
- Modify: `docs/superpowers/plans/2026-10-14-paper-v2-phase-d-data.md` Task 7 và 7b: "top 8" thành "top 5", ghi "chạy sau plan 2026-10-15-chunk-reading-unit"; Task 7 thêm bước đầu đo throughput rerank trên 200 câu và khối D7 (chunk theo từng mục = `chunk_document` với `target_chars=1`, không khôi phục chunker cũ) báo Hit@5 và nDCG@5

- [ ] **Step 1: Sửa tài liệu**

`grep -rn "hydrat\|top 8\|top-k 8\|chunk_risk\|gold_chunk_ids\|chunk_window" pharma-lab/docs backend/README.md README.md docs/superpowers/plans/2026-10-14-paper-v2-phase-d-data.md` và sửa từng chỗ.

- [ ] **Step 2: Kiểm và commit**

Run: lệnh grep trên trả về rỗng (trừ các dòng lịch sử trong `docs/research`).

```bash
git add pharma-lab/docs backend/README.md README.md docs/superpowers/plans
git commit -m "docs: chunks as the reading unit, five chunks per round"
```

---

## Self-review

- **Spec coverage §3.0c:** gộp mục và hằng số (Task 1); định danh theo tài liệu, bỏ `section_revisions`, Qdrant payload (Task 2); bỏ hydrate, `top_n = 5`, `max_evidence_chars = 60000`, citation một chunk, API và frontend (Task 3); nhãn chunk và hàng đánh giá (Task 4); bỏ nhãn mức chunk, nhóm `structured`, hit theo mục trong chunk, nhiều đơn vị một chunk (Task 5); golden v3, `rounds` theo section (Task 6); rag-final không chunk, `PIPELINE_VERSION` 0.4.0, bỏ index-only (Task 7); số đo token và dữ liệu dựng lại (Task 8); "top 8" thành 5 ở mọi tài liệu (Task 9).
- **Kiểu dữ liệu:** `Hit.section_keys`/`headings` (Task 3) được Task 4 đọc; `gold_chunk_label(document_key, ordinal)` (Task 4) được Task 6 dùng; payload search `{"document", "ordinal", "sections"}` (Task 3) được Task 6 đọc; `satisfied_units` (Task 5) được `one_round.coverage` dùng.
- **Review Focus:** mục 1, 2 có test ở Task 1; mục 3, 4 ở Task 5; mục 5 ở Task 3.
