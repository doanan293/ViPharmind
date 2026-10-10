# Kế hoạch thực thi: tổ chức, phân quyền, tự nạp nội dung và ra mắt

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đưa ViPharMind lên production với tổ chức và vai trò, collection có chủ sở hữu và mức hiển thị, người dùng tự soạn và xuất bản nội dung qua pipeline hiện có, superadmin và nhật ký, dữ liệu chuẩn hoá giữa Postgres và Qdrant, chạy trên Vercel và Google Cloud.

**Architecture:** Backend giữ kiến trúc sạch hiện có: domain thuần (`access`, `organizations`, `audit`, `corpus` mở rộng), application theo feature (không import chéo), infrastructure ghép nối (Postgres, Qdrant, DeepInfra, Cloud Tasks), api chỉ chạm infrastructure qua `api/deps.py`. Quyền được tính trong Postgres ở mỗi lượt hỏi và truyền xuống Qdrant dưới dạng bộ lọc release. Frontend thêm các feature `organizations`, `collections`, `audit`, `admin`, `legal` theo luật import một chiều.

**Tech Stack:** FastAPI, fastapi-users, SQLAlchemy 2 async, Alembic, Postgres, Qdrant, LangGraph, httpx, google-cloud-tasks, google-auth; React Router 8 SSR, TanStack Query, orval, Tiptap 3 (`@tiptap/markdown`), shadcn base-nova (core + block `dashboard-01`, TanStack Table), react-hook-form + zod, `@tailwindcss/typography`, Vitest browser + MSW, Playwright; Vercel (`@vercel/react-router`), Cloud Run, Cloud Tasks, Neon, Qdrant Cloud, DeepInfra.

**Spec:** `docs/superpowers/specs/2026-10-10-product-launch-design.md`

## Global Constraints

- Làm việc trực tiếp trên nhánh `dev`. Không thêm trailer `Co-Authored-By` vào commit.
- Trước mỗi commit backend: `uv run ruff format`, `uv run ruff check`, `uv run pyrefly check --min-severity warn` phải sạch; pre-commit chạy đúng các lệnh này và chặn commit nếu lỗi. Trước mỗi commit frontend: `npm run lint`, `npm run typecheck`, `npx prettier --check .` sạch.
- Lệnh test backend chạy từ `backend/`: unit `uv run pytest -q`; integration (cần Docker) `uv run pytest -q -m integration`. Frontend chạy từ `frontend/`: `npx vitest run`; e2e `npm run e2e`.
- Luật kiến trúc (`backend/tests/architecture/test_layering.py`): domain không import framework; application không import infrastructure, api, sqlalchemy, fastapi, httpx; **các feature trong `application/` không import nhau**; routers chỉ chạm infrastructure qua `api/deps.py`; `api/` không import `domain` trực tiếp.
- Luật kiến trúc frontend (`frontend/app/architecture.test.ts` và `.oxlintrc.json`): feature chỉ import feature khác theo bảng `ALLOWED_FEATURE_IMPORTS`; mỗi feature mới cần override oxlint riêng và phải được thêm vào danh sách cấm của mọi feature khác không được phép import nó.
- **Giao diện dùng hết hàng của shadcn (spec §8.1):** trước khi viết bất kỳ widget nào, tra registry (`npx shadcn@latest view <tên>`); có component hay block thì `npx shadcn@latest add` rồi sửa file CLI tải về (dữ liệu từ API, nhãn tiếng Việt, bỏ phần không dùng). Không đọc block rồi gõ lại thành component riêng. Không thêm registry thứ hai hay thư viện UI mới khi shadcn hoặc thư viện đã cài đáp ứng được. Form dùng react-hook-form + zod + `field`; bảng dùng `data-table` của block `dashboard-01`; danh sách dùng `item`/`empty`; lỗi dùng `alert`/`FieldError`.
- Mỗi chuỗi giao diện mới có cả `vi` và `en`. Mã lỗi mới của backend có khoá trong `errors.json` hai ngôn ngữ.
- Tài nguyên không được phép thấy trả **404**; thấy được nhưng thiếu quyền trả **403 `FORBIDDEN_ROLE`**.
- Hạn mức mặc định: 200.000 ký tự mỗi tài liệu, 100 tài liệu mỗi collection, 1.000.000 byte chữ và 5 collection mỗi người dùng, 5.000.000 byte chữ và 20 collection mỗi tổ chức.
- Lời mời hạn 7 ngày; token chỉ lưu dạng sha256.
- Spec quy định một migration 0016. Plan này tách thành 0016 (dọn corpus), 0017 (tổ chức, nhật ký, hạn mức), 0018 (chủ sở hữu collection, phạm vi hội thoại), 0019 (nội dung soạn, job) để mỗi lớp có commit xanh với `test_upgrade_head_matches_the_models`. Đây là quyết định có chủ ý của plan, không phải xung đột với spec.
- Chỉ superadmin đặt mức công khai. Superadmin cấp bằng CLI. Superadmin đọc hội thoại không ghi nhật ký.
- Production: Qwen3.5-9B cho mọi role LLM, Qwen3-Embedding-4B 2560 chiều, Qwen3-Reranker-4B qua DeepInfra; SMS tắt bằng `PHARMA_SMS__PROVIDER=none`.

## Review Focus

1. Một người dùng là owner của tổ chức A và member của tổ chức B hỏi một câu khi hội thoại đã thu hẹp vào một collection của A, rồi bị xoá khỏi A: lượt hỏi kế tiếp phải không trả về chunk nào của A và trả lời rằng không có nguồn (test ở Task D5).
2. Hai request `POST /collections/{id}/publish` song song cho cùng collection: chỉ một job được tạo, request kia nhận 409 `PUBLISH_IN_PROGRESS` (test ở Task E4).
3. Tài liệu Markdown chỉ gồm bảng, không có tiêu đề và không có đoạn văn: bundle vẫn có một mục với một block `table`, xuất bản thành công (test ở Task E2).
4. Lời mời được chấp nhận hai lần, hoặc nhận sau khi người mời đã bị xoá khỏi tổ chức: lần hai trả `INVITATION_NOT_PENDING`, lần nhận vẫn hợp lệ vì lời mời thuộc tổ chức, không thuộc người mời (test ở Task C2).
5. Cloud Tasks gọi lại endpoint nội bộ cho một job đã `ready`: phản hồi 200, không chạy lại pipeline, không tạo release mới (test ở Task E4).

## Sổ tên dùng chung (interface registry)

Các tên dưới đây được tạo ở task ghi trong ngoặc và được mọi task sau dùng nguyên văn.

| Tên | Nơi định nghĩa | Task |
| --- | --- | --- |
| `Transaction`, `TransactionFactory` | `domain/shared/transaction.py` | B2 |
| `Role`, `Actor`, các hàm `can_*` | `domain/access/` | B1 |
| `Organization`, `Membership`, `Invitation`, `InvitationStatus`, `MemberView` | `domain/organizations/models.py` | B2 |
| `OrganizationRepository`, `InvitationRepository` | `domain/organizations/ports.py` | B2 |
| `AuditEvent`, `AuditAction`, `AuditLog` | `domain/audit/` | B2 |
| `Visibility.ORGANIZATION`, `Collection.owner_organization_id`, `CollectionRepository` | `domain/corpus/models.py`, `ports.py` | D1, D2 |
| `SourceDocument`, `IngestJob`, `JobStatus`, `JobStep`, `SourceRepository`, `IngestJobRepository`, `JobDispatcher` | `domain/corpus/source.py` | E1 |
| `build_bundle`, `split_markdown`, `section_key`, `slugify` | `domain/corpus/authoring.py` | E2 |
| `ReleaseScope`, `Retriever.search_many(queries, top_k, scope)` | `domain/retrieval/` | D3 |
| `ActorResolver` | `application/access/service.py` | B4 |
| `OrganizationService`, `InvitationService` | `application/organizations/` | C1, C2 |
| `AuditService`, `AuditEventView`, `AuditPage` | `application/audit/service.py` | C3 |
| `CollectionService`, `CollectionView` | `application/corpus/collections.py` | D2 |
| `ContentService`, `PublishService` | `application/corpus/content.py`, `jobs.py` | E3, E4 |
| `ScopeResolver` | `application/chat/scope.py` | D3 |
| `AdminService` | `application/admin/service.py` | E6 |
| `IndexWriter.write(items, *, bundled, overwrite)` | `application/corpus/indexing.py` | A2 |

---

## Lớp A: chuẩn hoá corpus

### Task A1: Bỏ cột `embedding_text`, dọn `public.skills`, migration 0016

**Files:**
- Modify: `backend/src/pharma_agent/infrastructure/persistence/postgres/corpus_tables.py` (ChunkVersionTable)
- Modify: `backend/src/pharma_agent/infrastructure/persistence/postgres/corpus_repository.py` (`_chunk_row`, `index_items`)
- Modify: `backend/src/pharma_agent/infrastructure/retrieval/postgres_corpus.py` (`_record`)
- Create: `backend/src/pharma_agent/infrastructure/persistence/postgres/migrations/versions/0016_corpus_cleanup.py`
- Modify: `backend/tests/infrastructure/test_migrations.py`, `backend/tests/infrastructure/test_corpus_repository.py`, `backend/tests/infrastructure/test_postgres_corpus.py`

**Interfaces:**
- Consumes: `compose_embedding_text(*, context_header, chunk_text, colloquial, terms)` từ `domain/corpus/enrichment.py`; `ChunkVersion` (giữ trường `embedding_text` trong model domain, chỉ cột DB bị bỏ).
- Produces: hàm `embedding_text_of(row) -> str` trong `corpus_repository.py` dùng lại ở `postgres_corpus.py`.

- [ ] **Step 1: Test migration RED**

Thêm vào `backend/tests/infrastructure/test_migrations.py`:

```python
async def test_corpus_cleanup_dropped_the_cache_and_the_embedding_text(
    migrated_dsn: str,
) -> None:
    engine = create_async_engine(migrated_dsn)
    async with engine.connect() as connection:
        corpus_tables = await connection.run_sync(_tables, CORPUS_SCHEMA)
        columns = await connection.run_sync(_columns, "corpus.chunk_versions")
        public_tables = await connection.run_sync(_tables, None)
    await engine.dispose()
    assert "embedding_cache" not in corpus_tables
    assert "embedding_text" not in columns
    assert "embedding_text_sha256" in columns
    assert "skills" not in public_tables
```

Sửa `EXPECTED_CORPUS_TABLES` thành bộ 7 bảng, bỏ `"embedding_cache"`. Kiểm tra `_columns` nhận tên có schema; nếu helper hiện tại chỉ nhận tên bảng, đổi chữ ký thành `_columns(connection, table, schema=None)` và truyền `schema=CORPUS_SCHEMA`.

- [ ] **Step 2: Chạy để thấy FAIL**

Run: `cd backend && uv run pytest tests/infrastructure/test_migrations.py -q -m integration -k "cleanup or matches_the_models"`
Expected: FAIL, `embedding_cache` vẫn có và `embedding_text` vẫn có.

- [ ] **Step 3: Migration 0016**

```python
"""Corpus cleanup: vectors live only in Qdrant, embedding text is derived, drop leftovers.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-11 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CORPUS_TABLES = (
    "chunk_versions",
    "section_revisions",
    "release_chunks",
    "sections",
    "documents",
)


def upgrade() -> None:
    op.drop_table("embedding_cache", schema="corpus")
    op.drop_column("chunk_versions", "embedding_text", schema="corpus")
    # Left over from migrations removed in commit ab5d822; never part of the models.
    op.execute("DROP TABLE IF EXISTS public.skills")
    # VACUUM cannot run inside a transaction; Alembic opens one per migration.
    with op.get_context().autocommit_block():
        for table in CORPUS_TABLES:
            op.execute(f"VACUUM FULL corpus.{table}")


def downgrade() -> None:
    op.add_column(
        "chunk_versions",
        sa.Column("embedding_text", sa.Text(), nullable=False, server_default=""),
        schema="corpus",
    )
    op.alter_column(
        "chunk_versions", "embedding_text", server_default=None, schema="corpus"
    )
    op.create_table(
        "embedding_cache",
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("embedding_text_sha256", sa.String(length=64), nullable=False),
        sa.Column("dims", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "model", "embedding_text_sha256", name=op.f("pk_embedding_cache")
        ),
        schema="corpus",
    )
```

- [ ] **Step 4: Bỏ cột và bảng khỏi model**

Trong `corpus_tables.py`: xoá dòng `embedding_text: Mapped[str] = mapped_column(Text, nullable=False)` của `ChunkVersionTable` và xoá class `EmbeddingCacheTable`. Xoá file `infrastructure/persistence/postgres/embedding_cache.py`. Việc này làm `corpus_factory.py` không import được cho tới khi Task A2 xong, nên **Task A1 và A2 là một đơn vị, commit chung ở cuối A2**; `task-done` của A1 không chạy riêng.

Trong `corpus_repository.py`:

```python
from pharma_agent.domain.corpus.enrichment import compose_embedding_text
from pharma_agent.domain.retrieval.models import ColloquialMapping, TermAnnotation


def embedding_text_of(
    *,
    context_header: str,
    chunk_text: str,
    colloquial: dict[str, Any] | None,
    term_annotations: list[dict[str, Any]],
) -> str:
    """The text that was embedded, rebuilt from the stored columns (spec §4.9)."""
    return compose_embedding_text(
        context_header=context_header,
        chunk_text=chunk_text,
        colloquial=None
        if colloquial is None
        else ColloquialMapping.model_validate(colloquial),
        terms=[TermAnnotation.model_validate(item) for item in term_annotations],
    )
```

Xoá `"embedding_text": chunk.embedding_text,` khỏi `_chunk_row`. Trong `index_items`, thay `ChunkVersionTable.embedding_text` trong `select(...)` bằng `ChunkVersionTable.context_header, ChunkVersionTable.chunk_text, ChunkVersionTable.colloquial, ChunkVersionTable.term_annotations`, và khi dựng `IndexItem` đặt `embedding_text=embedding_text_of(context_header=row.context_header, chunk_text=row.chunk_text, colloquial=row.colloquial, term_annotations=row.term_annotations)`.

Trong `postgres_corpus.py` `_record(...)`: thay `embedding_text=chunk.embedding_text` bằng `embedding_text=embedding_text_of(context_header=chunk.context_header, chunk_text=chunk.chunk_text, colloquial=chunk.colloquial, term_annotations=chunk.term_annotations)`.

- [ ] **Step 5: Test repository RED→GREEN**

Thêm vào `tests/infrastructure/test_corpus_repository.py` (dùng fixture và snapshot sẵn có của file):

```python
async def test_index_items_rebuild_the_embedding_text(stack) -> None:
    snapshot = sample_snapshot()  # helper sẵn có của file; đổi tên theo file nếu khác
    release = await stack.repository.stage_release(
        snapshot, release_id=uuid.uuid4(), embedding_model="m", at=NOW
    )
    items = await stack.repository.index_items([release.id])
    expected = {chunk.id: chunk.embedding_text for chunk in snapshot.chunks}
    assert {item.chunk_version_id: item.embedding_text for item in items} == expected
```

Run: `cd backend && uv run pytest tests/infrastructure/test_corpus_repository.py tests/infrastructure/test_postgres_corpus.py tests/infrastructure/test_migrations.py -q -m integration`
Expected: PASS (sau khi Task A2 xong nếu commit chung).

### Task A2: Bỏ `EmbeddingCache`, nạp theo lô embed → ghi

**Files:**
- Modify: `backend/src/pharma_agent/domain/corpus/ports.py` (xoá `EmbeddingCache`)
- Modify: `backend/src/pharma_agent/domain/corpus/models.py` (`ReleaseStats`: bỏ `embeddings_cached`)
- Rewrite: `backend/src/pharma_agent/application/corpus/indexing.py`
- Modify: `backend/src/pharma_agent/application/corpus/import_bundle.py`, `service.py`
- Modify: `backend/src/pharma_agent/infrastructure/corpus_factory.py`
- Delete: `backend/src/pharma_agent/infrastructure/persistence/postgres/embedding_cache.py`
- Modify tests: `backend/tests/corpus_memory.py` (xoá cache in-memory), `tests/application/test_import_bundle.py`, `tests/application/test_corpus_service.py`, `tests/infrastructure/test_corpus_factory.py`, `tests/infrastructure/test_corpus_integration.py`

**Interfaces:**
- Produces:

```python
class IndexWriter:
    def __init__(self, index: VectorIndex, embedder: Embedder, *, batch_size: int, max_concurrent: int) -> None
    async def write(self, items: Sequence[IndexItem], *, bundled: Mapping[str, Sequence[float]], overwrite: bool = False) -> IndexCounts

class IndexCounts(frozen): upserted: int; updated: int; embeddings_from_bundle: int; embeddings_computed: int
class ImportKnowledgeBundle.__init__(self, repository, index, embedder, clock, *, embed_batch_size, embed_max_concurrent)
class CorpusService.__init__(...)  # cùng chữ ký, không còn cache
```

- [ ] **Step 1: Test RED cho IndexWriter**

Thay nội dung test về resolver/cache trong `tests/application/test_import_bundle.py` bằng:

```python
async def test_writer_embeds_only_new_points_and_uses_bundled_vectors() -> None:
    index = InMemoryVectorIndex()
    embedder = FakeEmbedder()
    items = [make_item(f"c{i}", f"text {i}") for i in range(5)]
    await index.upsert(
        items[:1],
        {items[0].embedding_text_sha256: fake_vector(items[0].embedding_text)},
    )
    bundled = {items[1].embedding_text_sha256: fake_vector(items[1].embedding_text)}
    writer = IndexWriter(index, embedder, batch_size=2, max_concurrent=2)
    counts = await writer.write(items, bundled=bundled)
    assert counts == IndexCounts(
        upserted=4, updated=1, embeddings_from_bundle=1, embeddings_computed=3
    )
    assert (
        embedder.calls
        == [
            [items[2].embedding_text, items[3].embedding_text],
            [items[4].embedding_text],
        ]
        or len(embedder.calls) == 2
    )
    assert set(index.points) == {item.chunk_version_id for item in items}


async def test_writer_rejects_a_wrong_dimension() -> None:
    index = InMemoryVectorIndex()
    writer = IndexWriter(
        index, WrongDimensionEmbedder(), batch_size=8, max_concurrent=1
    )
    with pytest.raises(CorpusImportError):
        await writer.write([make_item("c1", "t")], bundled={})
```

`FakeEmbedder` (`tests/fakes.py`) cần thêm `self.calls: list[list[str]]` ghi lại mỗi lô; `WrongDimensionEmbedder` trả vector 3 chiều với `dimension == 4`.

- [ ] **Step 2: Chạy RED**

Run: `cd backend && uv run pytest tests/application/test_import_bundle.py -q`
Expected: FAIL (`IndexWriter.__init__` không nhận `embedder`).

- [ ] **Step 3: Viết lại `indexing.py`**

```python
"""Embed and index the chunks of a release batch by batch.

Vectors never pile up in memory and never touch Postgres: each batch is embedded (or taken
from the bundle) and written to Qdrant at once. A rerun skips the points Qdrant already has.
"""

import asyncio
import itertools
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from pharma_agent.domain.corpus.models import CorpusImportError, IndexItem
from pharma_agent.domain.corpus.ports import Embedder, VectorIndex


class IndexCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    upserted: int
    updated: int
    embeddings_from_bundle: int
    embeddings_computed: int


class IndexWriter:
    def __init__(
        self,
        index: VectorIndex,
        embedder: Embedder,
        *,
        batch_size: int,
        max_concurrent: int,
    ) -> None:
        if batch_size < 1 or max_concurrent < 1:
            raise ValueError("batch_size and max_concurrent must be at least 1")
        self._index = index
        self._embedder = embedder
        self._batch_size = batch_size
        self._max_concurrent = max_concurrent

    async def write(
        self,
        items: Sequence[IndexItem],
        *,
        bundled: Mapping[str, Sequence[float]],
        overwrite: bool = False,
    ) -> IndexCounts:
        if overwrite:
            new, existing = list(items), []
        else:
            present = await self._index.existing_ids(
                [i.chunk_version_id for i in items]
            )
            new = [i for i in items if i.chunk_version_id not in present]
            existing = [i for i in items if i.chunk_version_id in present]
        batches = itertools.batched(new, self._batch_size)
        from_bundle = computed = 0
        lock = asyncio.Lock()

        async def worker() -> None:
            nonlocal from_bundle, computed
            for batch in batches:
                vectors: dict[str, Sequence[float]] = {}
                to_embed: list[str] = []
                for item in batch:
                    sha = item.embedding_text_sha256
                    if sha in vectors:
                        continue
                    if sha in bundled:
                        vectors[sha] = bundled[sha]
                    else:
                        to_embed.append(sha)
                texts = {i.embedding_text_sha256: i.embedding_text for i in batch}
                if to_embed:
                    embedded = await self._embedder.embed(
                        [texts[sha] for sha in to_embed]
                    )
                    dimension = self._embedder.dimension
                    if len(embedded) != len(to_embed) or any(
                        len(v) != dimension for v in embedded
                    ):
                        raise CorpusImportError(
                            f"embedding returned a wrong shape for model {self._embedder.model}"
                        )
                    vectors.update(zip(to_embed, embedded, strict=True))
                await self._index.upsert(batch, vectors)
                async with lock:
                    from_bundle += len(batch) - len(to_embed)
                    computed += len(to_embed)

        try:
            async with asyncio.TaskGroup() as group:
                for _ in range(self._max_concurrent):
                    group.create_task(worker())
        except ExceptionGroup as errors:
            raise errors.exceptions[0] from errors
        if existing:
            await self._index.set_release_ids(existing)
        return IndexCounts(
            upserted=len(new),
            updated=len(existing),
            embeddings_from_bundle=from_bundle,
            embeddings_computed=computed,
        )
```

`itertools.batched` trả iterator dùng chung cho các worker; mỗi `for batch in batches` lấy lô kế tiếp, không trùng.

- [ ] **Step 4: Sửa `import_bundle.py`, `service.py`, `corpus_factory.py`, `ports.py`, `models.py`**

- Xoá class `EmbeddingCache` trong `domain/corpus/ports.py`.
- `ReleaseStats`: xoá `embeddings_cached`.
- `ImportKnowledgeBundle.__init__(self, repository, index, embedder, clock, *, embed_batch_size, embed_max_concurrent)`: `self._writer = IndexWriter(index, embedder, batch_size=embed_batch_size, max_concurrent=embed_max_concurrent)`. `_build`: `items = await self._repository.index_items([release.id])`, `written = await self._writer.write(items, bundled=vectors)`, stats `model_copy(update={"embeddings_from_bundle": written.embeddings_from_bundle, "embeddings_computed": written.embeddings_computed, "points_upserted": written.upserted, "points_updated": written.updated})`.
- `CorpusService`: cùng constructor; `reindex` gọi `self._writer.write(items, bundled={}, overwrite=True)`.
- `corpus_factory.py`: xoá `PostgresEmbeddingCache`; truyền `embedder` vào hai service.
- Xoá `embedding_cache.py`. Xoá class cache in-memory trong `tests/corpus_memory.py` và mọi chỗ dùng.
- `cli.py`: nếu lệnh `corpus import` in `embeddings_cached`, bỏ dòng đó.

- [ ] **Step 5: GREEN và toàn bộ suite**

Run: `cd backend && uv run pytest -q && uv run pytest -q -m integration`
Expected: PASS toàn bộ. `test_corpus_integration` phải bỏ `TRUNCATE ... embedding_cache`.

- [ ] **Step 6: Commit (A1 và A2)**

```bash
git add backend
git commit -m "refactor(corpus): keep vectors only in Qdrant and derive the embedding text

Drops corpus.embedding_cache and chunk_versions.embedding_text (migration
0016), rebuilds the embedded text from the stored columns, and embeds
each batch right before writing it to Qdrant. Also drops the leftover
public.skills table."
```

### Task A3: Áp migration local và đo lại dung lượng

- [ ] **Step 1:** `cd backend && uv run pharma-agent migrate`
Expected: lên 0016, không lỗi.
- [ ] **Step 2:** Đo: `uv run python -c "..."` như câu lệnh đo đã dùng trong brainstorming, ghi con số vào `docs/superpowers/specs/2026-10-10-product-launch-design.md` mục 4.9 nếu khác đáng kể (chỉ sửa số, không sửa quyết định).
Expected: database dưới 120 MB.
- [ ] **Step 3:** Commit nếu spec thay đổi: `git commit -am "docs: record the corpus size after cleanup"`.

---

## Lớp B: domain `access`, `organizations`, `audit` và dữ liệu

### Task B1: Domain `access`

**Files:**
- Create: `backend/src/pharma_agent/domain/access/__init__.py`, `models.py`, `policy.py`
- Modify: `backend/src/pharma_agent/domain/corpus/models.py` (`Visibility.ORGANIZATION`, `Collection.owner_organization_id`)
- Test: `backend/tests/domain/access/test_policy.py`

**Interfaces:**
- Produces:

```python
# domain/access/models.py
class Role(StrEnum): OWNER = "owner"; EDITOR = "editor"; MEMBER = "member"
ROLE_RANK: dict[Role, int] = {Role.MEMBER: 0, Role.EDITOR: 1, Role.OWNER: 2}

@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID
    is_superadmin: bool
    memberships: Mapping[uuid.UUID, Role]   # organization_id -> role
    def role_in(self, organization_id: uuid.UUID) -> Role | None

# domain/access/policy.py — tất cả là hàm thuần, superadmin luôn True trừ can_leave và invite_needs_approval
def can_view_organization(actor, organization_id) -> bool
def can_manage_organization(actor, organization_id) -> bool          # đổi tên, xoá
def can_manage_members(actor, organization_id) -> bool               # đổi vai trò, xoá thành viên
def can_view_audit(actor, organization_id) -> bool                   # owner, editor
def invitable_roles(actor, organization_id) -> frozenset[Role]       # owner: all; editor: {editor, member}; member: {member}; ngoài: {}
def invite_needs_approval(actor, organization_id) -> bool            # True chỉ với member
def can_decide_invitation(actor, organization_id) -> bool            # duyệt/từ chối: owner, editor
def can_cancel_invitation(actor, organization_id, invited_by) -> bool # owner, editor, hoặc chính người mời
def can_leave(actor, organization_id, *, owner_count: int) -> bool   # member/editor: True; owner: owner_count > 1; không là thành viên: False
def can_view_collection(actor, collection: Collection) -> bool
def can_edit_collection(actor, collection: Collection) -> bool       # nội dung, tên, xoá
def can_set_visibility(actor, collection: Collection, visibility: Visibility) -> bool
def can_create_collection_for(actor, *, owner_user_id, owner_organization_id) -> bool
```

Quy tắc hiển thị (spec mục 3): `PUBLIC` ai cũng thấy; collection hệ thống (không chủ) chỉ superadmin sửa; collection cá nhân chỉ chủ thấy và sửa; collection tổ chức `PRIVATE` chỉ owner, editor thấy; `ORGANIZATION` mọi thành viên thấy; owner, editor sửa. `can_set_visibility`: `PUBLIC` chỉ superadmin; `ORGANIZATION` chỉ khi chủ là tổ chức; cá nhân chỉ `PRIVATE` (hoặc `PUBLIC` bởi superadmin).

- [ ] **Step 1: Sửa `Collection`**

Trong `domain/corpus/models.py`:

```python
class Visibility(StrEnum):
    PRIVATE = "private"
    ORGANIZATION = "organization"
    PUBLIC = "public"


class Collection(_Frozen):
    id: uuid.UUID
    key: str
    title: str
    owner_user_id: uuid.UUID | None = None
    owner_organization_id: uuid.UUID | None = None
    visibility: Visibility = Visibility.PRIVATE
    current_release_id: uuid.UUID | None = None

    @property
    def is_system(self) -> bool:
        return self.owner_user_id is None and self.owner_organization_id is None
```

- [ ] **Step 2: Test dạng bảng RED**

`backend/tests/domain/access/test_policy.py`:

```python
import uuid

import pytest

from pharma_agent.domain.access.models import Actor, Role
from pharma_agent.domain.access import policy
from pharma_agent.domain.corpus.models import Collection, Visibility

ORG = uuid.uuid4()
OTHER_ORG = uuid.uuid4()
ME = uuid.uuid4()
SOMEONE = uuid.uuid4()


def actor(role: Role | None, *, superadmin: bool = False) -> Actor:
    return Actor(ME, superadmin, {} if role is None else {ORG: role})


OWNER, EDITOR, MEMBER, OUTSIDER, ADMIN = (
    actor(Role.OWNER),
    actor(Role.EDITOR),
    actor(Role.MEMBER),
    actor(None),
    actor(None, superadmin=True),
)
ACTORS = [OWNER, EDITOR, MEMBER, OUTSIDER, ADMIN]


def col(**overrides: object) -> Collection:
    base: dict[str, object] = {"id": uuid.uuid4(), "key": "k", "title": "t"}
    return Collection(**{**base, **overrides})


SYSTEM = col(visibility=Visibility.PUBLIC)
MINE = col(owner_user_id=ME)
THEIRS = col(owner_user_id=SOMEONE)
ORG_PRIVATE = col(owner_organization_id=ORG)
ORG_SHARED = col(owner_organization_id=ORG, visibility=Visibility.ORGANIZATION)
OTHER_ORG_SHARED = col(
    owner_organization_id=OTHER_ORG, visibility=Visibility.ORGANIZATION
)


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        (
            lambda a: policy.can_view_organization(a, ORG),
            [True, True, True, False, True],
        ),
        (
            lambda a: policy.can_manage_organization(a, ORG),
            [True, False, False, False, True],
        ),
        (
            lambda a: policy.can_manage_members(a, ORG),
            [True, False, False, False, True],
        ),
        (lambda a: policy.can_view_audit(a, ORG), [True, True, False, False, True]),
        (
            lambda a: policy.invite_needs_approval(a, ORG),
            [False, False, True, False, False],
        ),
        (
            lambda a: policy.can_decide_invitation(a, ORG),
            [True, True, False, False, True],
        ),
        (
            lambda a: policy.can_cancel_invitation(a, ORG, invited_by=SOMEONE),
            [True, True, False, False, True],
        ),
        (
            lambda a: policy.can_cancel_invitation(a, ORG, invited_by=ME),
            [True, True, True, False, True],
        ),
        (
            lambda a: policy.can_leave(a, ORG, owner_count=1),
            [False, True, True, False, False],
        ),
        (
            lambda a: policy.can_leave(a, ORG, owner_count=2),
            [True, True, True, False, False],
        ),
    ],
)
def test_organization_rules(check, expected) -> None:
    assert [check(a) for a in ACTORS] == expected


def test_invitable_roles() -> None:
    assert policy.invitable_roles(OWNER, ORG) == frozenset(Role)
    assert policy.invitable_roles(EDITOR, ORG) == frozenset({Role.EDITOR, Role.MEMBER})
    assert policy.invitable_roles(MEMBER, ORG) == frozenset({Role.MEMBER})
    assert policy.invitable_roles(OUTSIDER, ORG) == frozenset()
    assert policy.invitable_roles(ADMIN, ORG) == frozenset(Role)


@pytest.mark.parametrize(
    ("collection", "view", "edit"),
    [
        (SYSTEM, [True] * 5, [False, False, False, False, True]),
        (MINE, [True] * 5, [True, True, True, True, True]),
        (
            THEIRS,
            [False, False, False, False, True],
            [False, False, False, False, True],
        ),
        (
            ORG_PRIVATE,
            [True, True, False, False, True],
            [True, True, False, False, True],
        ),
        (ORG_SHARED, [True, True, True, False, True], [True, True, False, False, True]),
        (
            OTHER_ORG_SHARED,
            [False, False, False, False, True],
            [False, False, False, False, True],
        ),
    ],
)
def test_collection_rules(collection, view, edit) -> None:
    assert [policy.can_view_collection(a, collection) for a in ACTORS] == view
    assert [policy.can_edit_collection(a, collection) for a in ACTORS] == edit


def test_only_superadmin_sets_public_and_organization_needs_an_org() -> None:
    assert not policy.can_set_visibility(OWNER, ORG_SHARED, Visibility.PUBLIC)
    assert policy.can_set_visibility(ADMIN, ORG_SHARED, Visibility.PUBLIC)
    assert policy.can_set_visibility(EDITOR, ORG_PRIVATE, Visibility.ORGANIZATION)
    assert not policy.can_set_visibility(MEMBER, ORG_PRIVATE, Visibility.ORGANIZATION)
    assert not policy.can_set_visibility(actor(None), MINE, Visibility.ORGANIZATION)
    assert not policy.can_set_visibility(ADMIN, MINE, Visibility.ORGANIZATION)
    assert policy.can_set_visibility(actor(None), MINE, Visibility.PRIVATE)


def test_create_collection_for_owner() -> None:
    assert policy.can_create_collection_for(
        OUTSIDER, owner_user_id=ME, owner_organization_id=None
    )
    assert not policy.can_create_collection_for(
        OUTSIDER, owner_user_id=SOMEONE, owner_organization_id=None
    )
    assert policy.can_create_collection_for(
        EDITOR, owner_user_id=None, owner_organization_id=ORG
    )
    assert not policy.can_create_collection_for(
        MEMBER, owner_user_id=None, owner_organization_id=ORG
    )
    assert policy.can_create_collection_for(
        ADMIN, owner_user_id=None, owner_organization_id=None
    )
    assert not policy.can_create_collection_for(
        OWNER, owner_user_id=None, owner_organization_id=None
    )
```

Lưu ý `MINE` với actor `ME`: trong bảng `test_collection_rules`, mọi actor đều là `ME` (chỉ khác membership), nên cột view và edit của `MINE` là `True` cho cả năm.

- [ ] **Step 3: Chạy RED**

Run: `cd backend && uv run pytest tests/domain/access -q`
Expected: FAIL `ModuleNotFoundError: pharma_agent.domain.access`.

- [ ] **Step 4: Implement**

`domain/access/models.py`:

```python
"""Who is acting: the user, their superadmin flag, and their role in each organization."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    MEMBER = "member"


ROLE_RANK: dict[Role, int] = {Role.MEMBER: 0, Role.EDITOR: 1, Role.OWNER: 2}


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID
    is_superadmin: bool
    memberships: Mapping[uuid.UUID, Role]

    def role_in(self, organization_id: uuid.UUID) -> Role | None:
        return self.memberships.get(organization_id)
```

`domain/access/policy.py`:

```python
"""The permission table of spec §3 as pure functions. Superadmin passes every check that
is about data; leaving and the approval rule are about membership, so they stay literal."""

import uuid

from pharma_agent.domain.access.models import ROLE_RANK, Actor, Role
from pharma_agent.domain.corpus.models import Collection, Visibility


def _at_least(actor: Actor, organization_id: uuid.UUID, role: Role) -> bool:
    if actor.is_superadmin:
        return True
    current = actor.role_in(organization_id)
    return current is not None and ROLE_RANK[current] >= ROLE_RANK[role]


def can_view_organization(actor: Actor, organization_id: uuid.UUID) -> bool:
    return _at_least(actor, organization_id, Role.MEMBER)


def can_manage_organization(actor: Actor, organization_id: uuid.UUID) -> bool:
    return _at_least(actor, organization_id, Role.OWNER)


def can_manage_members(actor: Actor, organization_id: uuid.UUID) -> bool:
    return _at_least(actor, organization_id, Role.OWNER)


def can_view_audit(actor: Actor, organization_id: uuid.UUID) -> bool:
    return _at_least(actor, organization_id, Role.EDITOR)


def invitable_roles(actor: Actor, organization_id: uuid.UUID) -> frozenset[Role]:
    if actor.is_superadmin:
        return frozenset(Role)
    match actor.role_in(organization_id):
        case Role.OWNER:
            return frozenset(Role)
        case Role.EDITOR:
            return frozenset({Role.EDITOR, Role.MEMBER})
        case Role.MEMBER:
            return frozenset({Role.MEMBER})
        case _:
            return frozenset()


def invite_needs_approval(actor: Actor, organization_id: uuid.UUID) -> bool:
    return not actor.is_superadmin and actor.role_in(organization_id) is Role.MEMBER


def can_decide_invitation(actor: Actor, organization_id: uuid.UUID) -> bool:
    return _at_least(actor, organization_id, Role.EDITOR)


def can_cancel_invitation(
    actor: Actor, organization_id: uuid.UUID, *, invited_by: uuid.UUID
) -> bool:
    if can_decide_invitation(actor, organization_id):
        return True
    return actor.role_in(organization_id) is not None and actor.user_id == invited_by


def can_leave(actor: Actor, organization_id: uuid.UUID, *, owner_count: int) -> bool:
    role = actor.role_in(organization_id)
    if role is None:
        return False
    return role is not Role.OWNER or owner_count > 1


def can_view_collection(actor: Actor, collection: Collection) -> bool:
    if actor.is_superadmin or collection.visibility is Visibility.PUBLIC:
        return True
    if collection.owner_user_id is not None:
        return collection.owner_user_id == actor.user_id
    if collection.owner_organization_id is not None:
        needed = (
            Role.MEMBER
            if collection.visibility is Visibility.ORGANIZATION
            else Role.EDITOR
        )
        return _at_least(actor, collection.owner_organization_id, needed)
    return False


def can_edit_collection(actor: Actor, collection: Collection) -> bool:
    if actor.is_superadmin:
        return True
    if collection.owner_user_id is not None:
        return collection.owner_user_id == actor.user_id
    if collection.owner_organization_id is not None:
        return _at_least(actor, collection.owner_organization_id, Role.EDITOR)
    return False


def can_set_visibility(
    actor: Actor, collection: Collection, visibility: Visibility
) -> bool:
    if visibility is Visibility.PUBLIC:
        return actor.is_superadmin
    if (
        visibility is Visibility.ORGANIZATION
        and collection.owner_organization_id is None
    ):
        return False
    if collection.is_system:
        return False
    return can_edit_collection(actor, collection)


def can_create_collection_for(
    actor: Actor,
    *,
    owner_user_id: uuid.UUID | None,
    owner_organization_id: uuid.UUID | None,
) -> bool:
    if owner_user_id is not None and owner_organization_id is not None:
        return False
    if owner_user_id is not None:
        return actor.is_superadmin or owner_user_id == actor.user_id
    if owner_organization_id is not None:
        return _at_least(actor, owner_organization_id, Role.EDITOR)
    return actor.is_superadmin
```

- [ ] **Step 5: GREEN**

Run: `cd backend && uv run pytest tests/domain/access tests/domain/corpus tests/architecture -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/pharma_agent/domain/access backend/src/pharma_agent/domain/corpus/models.py backend/tests/domain/access
git commit -m "feat(domain): add the access policy for organizations and collections"
```

### Task B2: Domain `organizations`, `audit` và `Transaction`

**Files:**
- Create: `backend/src/pharma_agent/domain/shared/transaction.py`
- Create: `backend/src/pharma_agent/domain/organizations/__init__.py`, `models.py`, `ports.py`
- Create: `backend/src/pharma_agent/domain/audit/__init__.py`, `models.py`, `ports.py`
- Test: `backend/tests/domain/organizations/test_models.py`

**Interfaces (Produces):**

```python
# domain/shared/transaction.py
class Transaction(Protocol):
    """Opaque handle for one database transaction; infrastructure knows the real type."""

class TransactionFactory(Protocol):
    def begin(self) -> AbstractAsyncContextManager[Transaction]: ...

# domain/organizations/models.py
INVITATION_TTL = timedelta(days=7)

class InvitationStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"; SENT = "sent"; ACCEPTED = "accepted"; DECLINED = "declined"
    REJECTED = "rejected"; REVOKED = "revoked"; EXPIRED = "expired"
OPEN_STATUSES = frozenset({PENDING_APPROVAL, SENT})

@dataclass(frozen=True) class Organization: id; name; text_quota_bytes: int | None; collection_quota: int | None; created_at; updated_at
@dataclass(frozen=True) class Membership: organization_id; user_id; role: Role; joined_at
@dataclass(frozen=True) class MemberView: user_id; display_name: str; email: str | None; role: Role; joined_at
@dataclass(frozen=True) class Invitation:
    id; organization_id; email; role; invited_by: uuid.UUID; status; token_hash: str
    created_at; expires_at: datetime | None; decided_by: uuid.UUID | None; decided_at: datetime | None
    def effective_status(self, now) -> InvitationStatus   # SENT quá expires_at -> EXPIRED
def generate_invitation_token() -> str          # secrets.token_urlsafe(32)
def invitation_token_hash(token: str) -> str    # sha256 hex
def organization_name_problem(name: str) -> str | None  # 1..100 ký tự sau strip

# domain/organizations/ports.py
class OrganizationRepository(Protocol):
    async def get(self, organization_id) -> Organization | None
    async def list_for_user(self, user_id) -> list[tuple[Organization, Role]]
    async def list_all(self, *, limit: int, cursor: tuple[datetime, str] | None) -> list[Organization]
    async def create(self, organization: Organization, owner_id: uuid.UUID, tx: Transaction) -> None
    async def rename(self, organization_id, name: str, now, tx) -> None
    async def set_quotas(self, organization_id, *, text_quota_bytes, collection_quota, now, tx) -> None
    async def delete(self, organization_id, tx) -> None
    async def members(self, organization_id) -> list[MemberView]
    async def memberships_of(self, user_id) -> dict[uuid.UUID, Role]
    async def owner_count(self, organization_id) -> int
    async def add_member(self, membership: Membership, tx) -> None
    async def set_role(self, organization_id, user_id, role: Role, tx) -> None
    async def remove_member(self, organization_id, user_id, tx) -> bool

class InvitationRepository(Protocol):
    async def get(self, invitation_id) -> Invitation | None
    async def get_by_token_hash(self, token_hash: str) -> Invitation | None
    async def list_for_organization(self, organization_id) -> list[Invitation]
    async def open_for(self, organization_id, email: str) -> Invitation | None
    async def create(self, invitation: Invitation, tx) -> None     # raise InvitationConflict khi đã có lời mời mở cho email
    async def update(self, invitation: Invitation, tx) -> None     # ghi status, token_hash, expires_at, decided_*

class InvitationConflict(DomainError): code = "INVITATION_CONFLICT"

# domain/audit/models.py
class AuditAction(StrEnum):
    ORGANIZATION_CREATED = "organization.created"; ORGANIZATION_RENAMED = "organization.renamed"; ORGANIZATION_DELETED = "organization.deleted"
    MEMBER_JOINED = "member.joined"; MEMBER_LEFT = "member.left"; MEMBER_REMOVED = "member.removed"; MEMBER_ROLE_CHANGED = "member.role_changed"
    INVITATION_CREATED = "invitation.created"; INVITATION_APPROVED = "invitation.approved"; INVITATION_REJECTED = "invitation.rejected"
    INVITATION_REVOKED = "invitation.revoked"; INVITATION_DECLINED = "invitation.declined"; INVITATION_RESENT = "invitation.resent"
    COLLECTION_CREATED = "collection.created"; COLLECTION_RENAMED = "collection.renamed"; COLLECTION_DELETED = "collection.deleted"
    COLLECTION_VISIBILITY_CHANGED = "collection.visibility_changed"; COLLECTION_PUBLISHED = "collection.published"; COLLECTION_ROLLED_BACK = "collection.rolled_back"
    DOCUMENT_CREATED = "document.created"; DOCUMENT_UPDATED = "document.updated"; DOCUMENT_DELETED = "document.deleted"
    GLOSSARY_UPDATED = "glossary.updated"; COLLOQUIAL_UPDATED = "colloquial.updated"
    USER_DISABLED = "user.disabled"; USER_ENABLED = "user.enabled"; QUOTA_CHANGED = "quota.changed"

@dataclass(frozen=True) class AuditEvent:
    id: uuid.UUID; occurred_at: datetime; actor_user_id: uuid.UUID | None; actor_was_superadmin: bool
    action: AuditAction; organization_id: uuid.UUID | None; subject_user_id: uuid.UUID | None
    collection_id: uuid.UUID | None; details: Mapping[str, object]
def new_event(actor: Actor, action, now, *, organization_id=None, subject_user_id=None, collection_id=None, **details) -> AuditEvent
    # actor_was_superadmin = actor.is_superadmin and (organization_id is None or actor.role_in(organization_id) is None)

# domain/audit/ports.py
class AuditLog(Protocol):
    async def record(self, event: AuditEvent, tx: Transaction) -> None
    async def for_organization(self, organization_id, *, limit, cursor: tuple[datetime, str] | None) -> list[AuditEvent]
    async def for_user(self, user_id, *, limit, cursor) -> list[AuditEvent]     # subject_user_id == user hoặc collection thuộc user: xem B3 (cột collection_owner_user_id)
    async def all(self, *, limit, cursor) -> list[AuditEvent]
```

Để `for_user` hiệu quả, `AuditEvent` thêm trường `subject_user_id` được **đặt bằng chủ sở hữu cá nhân của collection** khi sự kiện về collection cá nhân (service làm việc này), nên không cần join.

- [ ] **Step 1: Test RED**

```python
# tests/domain/organizations/test_models.py
from datetime import UTC, datetime, timedelta

from pharma_agent.domain.organizations.models import (
    INVITATION_TTL,
    Invitation,
    InvitationStatus,
    generate_invitation_token,
    invitation_token_hash,
    organization_name_problem,
)
import uuid

NOW = datetime(2026, 10, 11, tzinfo=UTC)


def invitation(status: InvitationStatus, expires_at: datetime | None) -> Invitation:
    return Invitation(
        uuid.uuid4(),
        uuid.uuid4(),
        "an@example.com",
        "member",
        uuid.uuid4(),
        status,
        "h",
        NOW,
        expires_at,
        None,
        None,
    )


def test_sent_invitations_expire_after_seven_days() -> None:
    sent = invitation(InvitationStatus.SENT, NOW + INVITATION_TTL)
    assert (
        sent.effective_status(NOW + INVITATION_TTL - timedelta(seconds=1))
        is InvitationStatus.SENT
    )
    assert sent.effective_status(NOW + INVITATION_TTL) is InvitationStatus.EXPIRED
    pending = invitation(InvitationStatus.PENDING_APPROVAL, None)
    assert (
        pending.effective_status(NOW + timedelta(days=30))
        is InvitationStatus.PENDING_APPROVAL
    )


def test_tokens_are_hashed_and_names_are_bounded() -> None:
    token = generate_invitation_token()
    assert len(token) >= 32 and invitation_token_hash(token) != token
    assert organization_name_problem("  ") == "the name is required"
    assert organization_name_problem("x" * 101) == "the name is too long"
    assert organization_name_problem(" Khoa Dược ") is None
```

- [ ] **Step 2: RED** — Run: `cd backend && uv run pytest tests/domain/organizations -q` → FAIL import.

- [ ] **Step 3: Implement** theo chữ ký ở Interfaces. `effective_status`: `if self.status is InvitationStatus.SENT and self.expires_at is not None and now >= self.expires_at: return EXPIRED`. `Invitation.role` kiểu `Role` (test trên truyền `"member"`, StrEnum chấp nhận khi so sánh; dùng `Role.MEMBER` trong test để pyrefly sạch).

- [ ] **Step 4: GREEN** — Run cùng lệnh + `tests/architecture` → PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(domain): add organizations, invitations, audit events and a transaction port"`.

### Task B3: Migration 0017 và bảng mới

**Files:**
- Modify: `backend/src/pharma_agent/infrastructure/persistence/postgres/tables.py`
- Create: `.../migrations/versions/0017_organizations_and_audit.py`
- Modify: `backend/tests/infrastructure/test_migrations.py`

**Interfaces (Produces):** các class `OrganizationTable`, `OrganizationMemberTable`, `OrganizationInvitationTable`, `AuditEventTable`; cột `user.text_quota_bytes`, `user.collection_quota`.

- [ ] **Step 1: Test RED**

Thêm `"organizations", "organization_members", "organization_invitations", "audit_events"` vào `EXPECTED_TABLES`, và:

```python
async def test_one_open_invitation_per_email_and_organization(
    migrated_dsn: str,
) -> None:
    engine = create_async_engine(migrated_dsn)
    org = uuid.uuid4()
    user = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO \"user\" (id, email, hashed_password, is_active, is_superuser, is_verified) VALUES (:id, :email, 'x', true, false, true)"
            ),
            {"id": user, "email": f"{user.hex}@example.com"},
        )
        await connection.execute(
            text(
                "INSERT INTO organizations (id, name, created_at, updated_at) VALUES (:id, 'Org', now(), now())"
            ),
            {"id": org},
        )
        insert = text(
            "INSERT INTO organization_invitations (id, organization_id, email, role, invited_by, status, token_hash, created_at) VALUES (gen_random_uuid(), :org, 'a@b.c', 'member', :user, :status, md5(random()::text), now())"
        )
        await connection.execute(insert, {"org": org, "user": user, "status": "sent"})
        await connection.execute(
            insert, {"org": org, "user": user, "status": "declined"}
        )
        with pytest.raises(IntegrityError):
            await connection.execute(
                insert, {"org": org, "user": user, "status": "pending_approval"}
            )
    await engine.dispose()
```

- [ ] **Step 2: RED** — Run: `uv run pytest tests/infrastructure/test_migrations.py -q -m integration` → FAIL.

- [ ] **Step 3: Tables**

```python
class OrganizationTable(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    text_quota_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    collection_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class OrganizationMemberTable(Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'editor', 'member')", name="role"),
        Index("ix_organization_members_user_id", "user_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OrganizationInvitationTable(Base):
    __tablename__ = "organization_invitations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_approval','sent','accepted','declined','rejected','revoked','expired')",
            name="status",
        ),
        Index(
            "uq_organization_invitations_open",
            "organization_id",
            "email",
            unique=True,
            postgresql_where=text("status IN ('pending_approval', 'sent')"),
        ),
        Index("ix_organization_invitations_token_hash", "token_hash", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuditEventTable(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index(
            "ix_audit_events_organization_occurred",
            "organization_id",
            "occurred_at",
            "id",
        ),
        Index(
            "ix_audit_events_subject_occurred", "subject_user_id", "occurred_at", "id"
        ),
        Index("ix_audit_events_occurred", "occurred_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    actor_was_superadmin: Mapped[bool] = mapped_column(Boolean, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    subject_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    collection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
```

`organization_id`, `subject_user_id`, `collection_id` của nhật ký **không có FK**, để sự kiện còn lại sau khi đối tượng bị xoá. `invited_by` của lời mời là `SET NULL` để lời mời sống tiếp khi người mời xoá tài khoản (Review Focus 4). `UserTable` thêm `text_quota_bytes: Mapped[int | None]` (BigInteger) và `collection_quota: Mapped[int | None]`.

- [ ] **Step 4: Migration 0017** — dùng `op.create_table` cho bốn bảng với cột như trên (`sa.BigInteger()`, `postgresql.JSONB`), `op.create_index(..., postgresql_where=sa.text("status IN ('pending_approval', 'sent')"), unique=True)`, `op.add_column("user", sa.Column("text_quota_bytes", sa.BigInteger(), nullable=True))`, `op.add_column("user", sa.Column("collection_quota", sa.Integer(), nullable=True))`. `downgrade` ngược lại.

- [ ] **Step 5: GREEN** — Run: `uv run pytest tests/infrastructure/test_migrations.py -q -m integration` → PASS, `_diff == []`.

- [ ] **Step 6: Commit** — `git commit -m "feat(db): add organizations, members, invitations, audit events and quota columns"`.

### Task B4: Repository Postgres, `ActorResolver`, fakes

**Files:**
- Create: `backend/src/pharma_agent/infrastructure/persistence/postgres/transaction.py`, `organization_repository.py`, `invitation_repository.py`, `audit_log.py`
- Create: `backend/src/pharma_agent/application/access/__init__.py`, `service.py`
- Create: `backend/tests/organization_fakes.py`
- Test: `backend/tests/infrastructure/test_organizations_postgres.py`, `backend/tests/application/test_actor_resolver.py`

**Interfaces (Produces):**

```python
# infrastructure/persistence/postgres/transaction.py
class PostgresTransactionFactory:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[AsyncSession]   # `async with sessions.begin() as session: yield session`
def session_of(tx: Transaction) -> AsyncSession              # isinstance check, raise TypeError otherwise

# application/access/service.py
class ActorResolver:
    def __init__(self, accounts: AccountRepository, organizations: OrganizationRepository) -> None
    async def resolve(self, user_id: uuid.UUID) -> Actor      # AccountNotFound nếu không có user; memberships từ repo
```

Fakes (`tests/organization_fakes.py`): `InMemoryTx` (factory `begin()` yield một object và, khi exception thoát khối, **hoàn tác** các thay đổi: đơn giản nhất là các repo in-memory ghi vào `tx.pending: list[Callable[[], None]]` và factory áp dụng khi thoát không lỗi), `InMemoryOrganizations`, `InMemoryInvitations`, `InMemoryAuditLog`, và `build_org_fakes()`.

- [ ] **Step 1: Test integration RED** (`test_organizations_postgres.py`, `pytestmark = integration`): tạo user bằng `add_user` như `test_account_postgres.py`; tạo org với owner qua `create(org, owner, tx)`; `members()` trả owner với `display_name`; `memberships_of(owner)`; `owner_count` 1; thêm member, `set_role`, `remove_member`; `delete` xoá thành viên theo cascade; lời mời `create` hai lần cùng email mở → `InvitationConflict`; `open_for`; `get_by_token_hash`; audit `record` trong cùng tx với `rename` rồi raise → cả hai không ghi (test tính nguyên tử):

```python
async def test_audit_and_change_commit_together(database: Database) -> None:
    repo, audit, tx = make(database)
    org = await seed_org(database, repo, tx)
    with pytest.raises(RuntimeError):
        async with tx.begin() as t:
            await repo.rename(org.id, "Renamed", NOW, t)
            await audit.record(event(org.id), t)
            raise RuntimeError("boom")
    assert (await repo.get(org.id)).name == org.name
    assert await audit.for_organization(org.id, limit=10, cursor=None) == []
```

- [ ] **Step 2: RED** → import error.

- [ ] **Step 3: Implement** repositories bằng SQLAlchemy Core qua `__table__.c` như `account_repository.py` (fastapi-users typing). `members()` join `user` lấy `display_name`, `email`. `list_all` phân trang keyset theo `(created_at, id)`. `AuditLog.for_*` keyset `(occurred_at desc, id desc)` với `cursor: (datetime, str)`; `limit` do caller cộng 1. `record` dùng `session_of(tx).execute(insert(AuditEventTable).values(...))` với `details=dict(event.details)`.

- [ ] **Step 4: ActorResolver test** (unit, fakes): user không tồn tại → `AccountNotFound`; user có 2 membership → `Actor.memberships` đúng; `is_superuser` → `is_superadmin`.

- [ ] **Step 5: GREEN** — Run: `uv run pytest tests/application/test_actor_resolver.py -q && uv run pytest tests/infrastructure/test_organizations_postgres.py -q -m integration` → PASS.

- [ ] **Step 6: Commit** — `git commit -m "feat(infra): persist organizations, invitations and audit events in one transaction"`.

---

## Lớp C: service tổ chức, lời mời, nhật ký và API

### Task C1: `OrganizationService`

**Files:**
- Create: `backend/src/pharma_agent/application/organizations/__init__.py`, `errors.py`, `service.py`
- Test: `backend/tests/application/test_organization_service.py`

**Interfaces (Produces):**

```python
# application/organizations/errors.py (ApplicationError con)
class OrganizationNotFound: code = "ORGANIZATION_NOT_FOUND"       # 404
class ForbiddenRole: code = "FORBIDDEN_ROLE"                       # 403
class LastOwner: code = "LAST_OWNER"                               # 409
class AlreadyMember: code = "ALREADY_MEMBER"                       # 409
class MemberNotFound: code = "MEMBER_NOT_FOUND"                    # 404
class InvitationNotFound: code = "INVITATION_NOT_FOUND"            # 404
class InvitationExpired: code = "INVITATION_EXPIRED"               # 409
class InvitationNotPending: code = "INVITATION_NOT_PENDING"        # 409
class InvitationEmailMismatch: code = "INVITATION_EMAIL_MISMATCH"  # 409
class InvitationAlreadyOpen: code = "INVITATION_ALREADY_OPEN"      # 409
class OrganizationNameInvalid(InvalidInput): code = "ORGANIZATION_NAME_INVALID"

# application/organizations/service.py
class OrganizationView(BaseModel): id; name; role: Role | None; member_count: int; created_at
class MemberItem(BaseModel): user_id; display_name; email: str | None; role: Role; joined_at
class OrganizationService:
    def __init__(self, *, organizations: OrganizationRepository, audit: AuditLog, tx: TransactionFactory, clock: Clock) -> None
    async def list_mine(self, actor) -> list[OrganizationView]
    async def get(self, actor, organization_id) -> OrganizationView             # 404 nếu không thấy
    async def create(self, actor, name) -> OrganizationView                      # actor là owner; audit ORGANIZATION_CREATED
    async def rename(self, actor, organization_id, name) -> OrganizationView    # can_manage_organization; audit
    async def delete(self, actor, organization_id, *, confirm_name: str) -> None # tên phải trùng; audit trước khi xoá (event giữ organization_id)
    async def members(self, actor, organization_id) -> list[MemberItem]
    async def set_role(self, actor, organization_id, user_id, role) -> None      # LastOwner nếu hạ owner cuối
    async def remove_member(self, actor, organization_id, user_id) -> None       # LastOwner nếu owner cuối
    async def leave(self, actor, organization_id) -> None                        # can_leave; audit MEMBER_LEFT
```

Quy tắc 404 so với 403: nếu `can_view_organization` sai thì raise `OrganizationNotFound` kể cả khi tổ chức tồn tại; nếu thấy mà thiếu quyền thì `ForbiddenRole`. Viết helper `_visible(actor, organization_id) -> Organization` dùng ở mọi phương thức.

- [ ] **Step 1: Test RED**

```python
# tests/application/test_organization_service.py (fakes từ tests/organization_fakes.py)
async def test_creator_is_the_first_owner_and_sees_the_org() -> None:
    service, fakes, me = build()
    view = await service.create(actor(me), "Khoa Dược")
    assert view.role is Role.OWNER and view.member_count == 1
    assert [v.id for v in await service.list_mine(actor(me))] == [view.id]
    assert fakes.audit.actions() == [AuditAction.ORGANIZATION_CREATED]


async def test_outsiders_get_404_and_members_get_403() -> None:
    service, fakes, me = build()
    org = await service.create(actor(me), "Org")
    stranger = uuid.uuid4()
    with pytest.raises(OrganizationNotFound):
        await service.get(actor(stranger), org.id)
    member = uuid.uuid4()
    fakes.organizations.seed_member(org.id, member, Role.MEMBER)
    with pytest.raises(ForbiddenRole):
        await service.rename(actor(member, {org.id: Role.MEMBER}), org.id, "X")


async def test_the_last_owner_cannot_be_demoted_removed_or_leave() -> None:
    service, fakes, me = build()
    org = await service.create(actor(me), "Org")
    owner = actor(me, {org.id: Role.OWNER})
    with pytest.raises(LastOwner):
        await service.set_role(owner, org.id, me, Role.EDITOR)
    with pytest.raises(LastOwner):
        await service.leave(owner, org.id)
    other = uuid.uuid4()
    fakes.organizations.seed_member(org.id, other, Role.OWNER)
    await service.leave(owner, org.id)  # giờ còn owner khác
    assert fakes.organizations.role_of(org.id, me) is None
    assert fakes.audit.actions()[-1] == AuditAction.MEMBER_LEFT


async def test_delete_needs_the_exact_name_and_records_before_deleting() -> None:
    service, fakes, me = build()
    org = await service.create(actor(me), "Org")
    owner = actor(me, {org.id: Role.OWNER})
    with pytest.raises(InvalidInput):
        await service.delete(owner, org.id, confirm_name="org")
    await service.delete(owner, org.id, confirm_name="Org")
    assert await fakes.organizations.get(org.id) is None
    assert fakes.audit.events[-1].organization_id == org.id


async def test_a_failed_change_leaves_no_audit_event() -> None:
    service, fakes, me = build()
    org = await service.create(actor(me), "Org")
    fakes.organizations.fail_next = True
    with pytest.raises(RuntimeError):
        await service.rename(actor(me, {org.id: Role.OWNER}), org.id, "New")
    assert fakes.audit.actions() == [AuditAction.ORGANIZATION_CREATED]
```

`build()` tạo service với fakes và trả `(service, fakes, me_uuid)`; `actor(user_id, memberships=None)` tạo `Actor`.

- [ ] **Step 2: RED** → import error.
- [ ] **Step 3: Implement** theo Interfaces. Mọi thao tác ghi: `async with self._tx.begin() as tx: await repo...(tx); await self._audit.record(new_event(...), tx)`. `set_role`/`remove_member`: nếu đối tượng là owner và `owner_count == 1` → `LastOwner`. `leave`: `can_leave(actor, org_id, owner_count=...)`, nếu không là thành viên → `OrganizationNotFound`, nếu owner cuối → `LastOwner`.
- [ ] **Step 4: GREEN** — `uv run pytest tests/application/test_organization_service.py tests/architecture -q`.
- [ ] **Step 5: Commit** — `git commit -m "feat(organizations): create, rename, delete organizations and manage members"`.

### Task C2: `InvitationService` và email lời mời

**Files:**
- Create: `backend/src/pharma_agent/application/organizations/invitations.py`, `messages.py`
- Test: `backend/tests/application/test_invitation_service.py`, `backend/tests/application/test_invitation_messages.py`

**Interfaces (Produces):**

```python
class InvitationView(BaseModel): id; organization_id; email; role; status: InvitationStatus; invited_by_name: str; created_at; expires_at
class InvitationPreview(BaseModel): organization_name: str; inviter_name: str; role: Role; email_hint: str  # "a***@example.com"
class InvitationPolicy(frozen): invites_per_inviter_per_hour: int = 20; invites_per_email_per_hour: int = 5; frontend_url: str
class InvitationService:
    def __init__(self, *, organizations: OrganizationRepository, invitations: InvitationRepository, accounts: AccountRepository,
                 audit: AuditLog, tx: TransactionFactory, email: EmailSender, limiter: RateLimiter, clock: Clock, policy: InvitationPolicy) -> None
    async def list(self, actor, organization_id) -> list[InvitationView]          # can_view_organization; member chỉ thấy lời mời của chính mình
    async def invite(self, actor, organization_id, email, role, *, locale) -> InvitationView
    async def approve(self, actor, organization_id, invitation_id, *, locale) -> InvitationView
    async def reject(self, actor, organization_id, invitation_id) -> InvitationView
    async def revoke(self, actor, organization_id, invitation_id) -> InvitationView
    async def resend(self, actor, organization_id, invitation_id, *, locale) -> InvitationView
    async def preview(self, token) -> InvitationPreview                             # không cần đăng nhập; 404 nếu không mở
    async def accept(self, actor, token) -> OrganizationView                        # email đã xác minh phải trùng
    async def decline(self, actor, token) -> None
```

Luồng `invite`: `normalize_email`; `invitable_roles(actor, org)` phải chứa `role` (sai → `ForbiddenRole`); email đã là thành viên → `AlreadyMember`; đã có lời mời mở → `InvitationAlreadyOpen`; nếu `invite_needs_approval` → tạo `PENDING_APPROVAL` không gửi mail, audit `INVITATION_CREATED` với `details={"needs_approval": True}`; ngược lại `_send(invitation, locale)`: rate limit `invite-by:{actor.user_id}` và `invite-to:{email}` qua `limiter.acquire`, sinh token, `expires_at = now + INVITATION_TTL`, gửi email với link `{frontend_url}/invitations/{token}`, lưu `token_hash`, trạng thái `SENT`. `approve` = `_send` cho lời mời `PENDING_APPROVAL`, audit `INVITATION_APPROVED`. `resend` sinh token mới (token cũ vô hiệu), gia hạn, audit `INVITATION_RESENT`. `accept`: tìm theo hash; `effective_status` phải là `SENT` (EXPIRED → `InvitationExpired`, khác → `InvitationNotPending`); tài khoản của actor phải có `email_verified` và `email == invitation.email` (sai → `InvitationEmailMismatch`); đã là thành viên → đánh dấu `ACCEPTED` và trả view (idempotent về mặt membership nhưng lần hai ở trạng thái `ACCEPTED` → `InvitationNotPending`, Review Focus 4); thêm membership với `role`, audit `MEMBER_JOINED` với `details={"via": "invitation"}`.

`messages.py`: `invitation_email(organization_name, inviter_name, role, link, locale) -> EmailContent`. Tạo module gốc `application/mail.py` chứa `EmailContent` và `html_message(subject, body, highlight=None)` (chuyển `_html` và `EmailContent` từ `application/account/messages.py` sang đó, `account/messages.py` import lại). Module gốc của `application/` được mọi feature dùng chung, hợp luật kiến trúc.

- [ ] **Step 1: Test RED** (các ca: owner mời gửi mail ngay với link chứa token; member mời thì chờ duyệt và không có mail; editor duyệt thì mail đi; editor không mời được owner → `ForbiddenRole`; mời email đã là thành viên → `AlreadyMember`; mời trùng → `InvitationAlreadyOpen`; accept bằng tài khoản email khác → `InvitationEmailMismatch`; accept sau 7 ngày → `InvitationExpired`; accept hai lần → lần hai `InvitationNotPending`; người mời bị xoá khỏi tổ chức rồi người được mời vẫn accept được; resend làm token cũ 404; rate limit 6 lần tới cùng email trong một giờ → `RateLimited`).

```python
async def test_owner_invite_sends_a_link_and_accepting_joins() -> None:
    s, f, owner_id, org = await build_with_org()
    view = await s.invite(
        owner(org), org.id, "New@Example.com ", Role.EDITOR, locale="vi"
    )
    assert view.status is InvitationStatus.SENT and view.email == "new@example.com"
    link = f.email.sent[-1].text.split("http", 1)[1]
    token = link.rsplit("/", 1)[1].strip()
    invitee = f.accounts.add(email="new@example.com", email_verified=True)
    joined = await s.accept(Actor(invitee.id, False, {}), token)
    assert joined.role is Role.EDITOR
    with pytest.raises(InvitationNotPending):
        await s.accept(Actor(invitee.id, False, {}), token)
```

- [ ] **Step 2: RED**, **Step 3: Implement**, **Step 4: GREEN** (`uv run pytest tests/application/test_invitation_service.py tests/application/test_invitation_messages.py tests/application/test_account_messages.py tests/architecture -q`).
- [ ] **Step 5: Commit** — `git commit -m "feat(organizations): invite by email with approval for member invites"`.

### Task C3: `AuditService`

**Files:**
- Create: `backend/src/pharma_agent/application/audit/__init__.py`, `service.py`
- Test: `backend/tests/application/test_audit_service.py`

**Interfaces (Produces):**

```python
class AuditEventView(BaseModel): id; occurred_at; actor_user_id: uuid.UUID | None; actor_name: str; actor_was_superadmin: bool
                                 action: AuditAction; organization_id; subject_user_id; collection_id; details: dict[str, Any]
class AuditPage(BaseModel): items: list[AuditEventView]; next_cursor: str | None
class AuditService:
    def __init__(self, *, audit: AuditLog, accounts: AccountRepository, clock: Clock) -> None
    async def for_organization(self, actor, organization_id, *, limit, cursor) -> AuditPage   # can_view_audit, else ForbiddenRole; không thấy org → OrganizationNotFound (cần OrganizationRepository → thêm tham số `organizations`)
    async def mine(self, actor, *, limit, cursor) -> AuditPage
    async def everything(self, actor, *, limit, cursor) -> AuditPage                         # chỉ superadmin, else ForbiddenRole
```

Cursor dùng `encode_cursor(occurred_at, id.hex)` / `decode_cursor` của `application/pagination.py`. `actor_name` lấy từ `accounts.get(actor_user_id)` theo lô (gom id, một `get` mỗi id là chấp nhận được với trang 50; thêm `AccountRepository.get_many(ids) -> dict` **không** cần ở bước này).

- [ ] **Step 1: Test RED** (3 ca: member không xem được nhật ký tổ chức; trang 2 nối tiếp đúng theo cursor; `mine` chỉ trả sự kiện có `subject_user_id == me`).
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** — `git commit -m "feat(audit): read organization, personal and global audit logs"`.

### Task C4: API tổ chức, lời mời, nhật ký; container; lỗi

**Files:**
- Create: `backend/src/pharma_agent/api/routers/organizations.py`, `invitations.py`, `audit.py`
- Modify: `backend/src/pharma_agent/api/deps.py`, `api/errors.py`, `api/app.py`
- Modify: `backend/src/pharma_agent/infrastructure/container.py`, create `infrastructure/organizations_factory.py`
- Test: `backend/tests/api/test_organizations_api_postgres.py`

**Interfaces (Produces):**

```python
# api/deps.py
async def current_actor(user_id: UserId, container: ContainerDep) -> Actor   # container.actors.resolve(uuid)
CurrentActor = Annotated[Actor, Depends(current_actor)]   # api không import domain: dùng `from pharma_agent.application.access.service import Actor` (re-export Actor ở application/access/service.py)
def require_organizations(container) -> OrganizationService
def require_invitations(container) -> InvitationService
def require_audit(container) -> AuditService
# container.py: Container thêm actors: ActorResolver | None, organizations, invitations, audit, tx
# infrastructure/organizations_factory.py
def build_organization_services(settings, sessions, *, clock, email) -> tuple[ActorResolver, OrganizationService, InvitationService, AuditService]
```

Routes và tên (operationId cho orval):

| Method, path | name |
| --- | --- |
| `GET /organizations` | `organizations:list` |
| `POST /organizations` (201) | `organizations:create` |
| `GET /organizations/{organization_id}` | `organizations:get` |
| `PATCH /organizations/{organization_id}` body `{name}` | `organizations:rename` |
| `DELETE /organizations/{organization_id}` body `{confirm_name}` (DELETE với JSON body: FastAPI, httpx, `fetch` và orval đều hỗ trợ) | `organizations:delete` |
| `GET /organizations/{organization_id}/members` | `organizations:members.list` |
| `PATCH /organizations/{organization_id}/members/{user_id}` body `{role}` | `organizations:members.set_role` |
| `DELETE /organizations/{organization_id}/members/{user_id}` | `organizations:members.remove` |
| `POST /organizations/{organization_id}/leave` (204) | `organizations:leave` |
| `GET /organizations/{organization_id}/invitations` | `invitations:list` |
| `POST /organizations/{organization_id}/invitations` body `{email, role}` (201) | `invitations:create` |
| `POST .../invitations/{invitation_id}/approve` `/reject` `/revoke` `/resend` | `invitations:approve` … |
| `GET /invitations/{token}` (công khai) | `invitations:preview` |
| `POST /invitations/{token}/accept` → `OrganizationView` | `invitations:accept` |
| `POST /invitations/{token}/decline` (204) | `invitations:decline` |
| `GET /organizations/{organization_id}/audit?limit&cursor` | `audit:organization` |
| `GET /account/audit?limit&cursor` | `audit:mine` |

`STATUS_BY_ERROR` thêm: `ForbiddenRole: 403`, `OrganizationNotFound: 404`, `MemberNotFound: 404`, `InvitationNotFound: 404`, `LastOwner/AlreadyMember/InvitationExpired/InvitationNotPending/InvitationEmailMismatch/InvitationAlreadyOpen: 409`.

- [ ] **Step 1: Test RED** (`postgres_app`): đăng ký A và B; A tạo org; B gọi `GET /organizations/{id}` → 404; A mời B qua `POST .../invitations`; đọc token từ `outbox.email`; B `GET /invitations/{token}` không đăng nhập → 200 với `email_hint`; B accept → 200 và `GET /organizations` của B có org với `role=member`; B `PATCH /organizations/{id}` → 403 `FORBIDDEN_ROLE`; A `GET .../audit` có `member.joined`; B `GET .../audit` → 403.

```python
async def test_outsiders_see_404_on_every_organization_route(migrated_dsn: str) -> None:
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        a, b = new_email(), new_email()
        await verified_register(client, outbox, a)
        org = (
            await client.post(
                "/api/v1/organizations",
                json={"name": "Org"},
                headers=csrf_header(client),
            )
        ).json()
        client.cookies.clear()
        await verified_register(client, outbox, b)
        headers = csrf_header(client)
        base = f"/api/v1/organizations/{org['id']}"
        calls = [
            client.get(base),
            client.patch(base, json={"name": "x"}, headers=headers),
            client.get(f"{base}/members"),
            client.get(f"{base}/invitations"),
            client.post(
                f"{base}/invitations",
                json={"email": "c@example.com", "role": "member"},
                headers=headers,
            ),
            client.get(f"{base}/audit"),
            client.post(f"{base}/leave", headers=headers),
        ]
        for coroutine in calls:
            response = await coroutine
            assert response.status_code == 404, response.text
```

- [ ] **Step 2: RED**, **Step 3: Implement** router theo mẫu `account.py` (body models Pydantic, `problem_responses`), **Step 4: GREEN**: `uv run pytest tests/api -q -m integration && uv run pytest -q`.
- [ ] **Step 5: Commit** — `git commit -m "feat(api): organizations, invitations and audit endpoints"`.

### Task C5: `/users/me` mở rộng và CLI superadmin

**Files:**
- Modify: `backend/src/pharma_agent/application/account/service.py` (`AccountView`), `domain/account/ports.py` (`AccountRepository.set_superuser(user_id, value)`), `infrastructure/persistence/postgres/account_repository.py`, `cli.py`
- Modify: `backend/src/pharma_agent/infrastructure/account_factory.py` (truyền `memberships: MembershipLookup`)
- Test: `backend/tests/application/test_account_service.py`, `backend/tests/test_cli.py`

**Interfaces (Produces):**

```python
class MembershipView(BaseModel): organization_id: uuid.UUID; name: str; role: Role
class AccountView: ... + is_superadmin: bool (= is_superuser); memberships: list[MembershipView]; phone_sign_in_enabled: bool
# domain/organizations/ports.py
class MembershipLookup(Protocol):
    async def list_for_user(self, user_id) -> list[tuple[Organization, Role]]   # OrganizationRepository đã có cùng tên
# AccountService.__init__ thêm memberships: MembershipLookup | None = None, policy.sms_enabled: bool = True
# cli: pharma-agent superadmin grant <email> | revoke <email> | list
```

`get_account` gọi `self._memberships.list_for_user(user_id)` khi có. `phone_sign_in_enabled = self._policy.sms_enabled`. `request_phone_login`/`request_phone_change` khi `sms_enabled` False → `PhoneSignInDisabled(ServiceUnavailable)` code `PHONE_SIGN_IN_DISABLED` (map 503). `AccountSettings`/`SmsSettings.provider: Literal["log", "none"]`; `sms_enabled = settings.sms.provider != "none"`.

- [ ] **Step 1: Test RED** — unit: `get_account` trả memberships từ fake lookup; `phone_sign_in_enabled=False` → `request_phone_login` raise `PhoneSignInDisabled`; CLI: `superadmin grant` với email không có → exit 1; có → `is_superuser` True (test_cli dùng fake repo qua monkeypatch như các test CLI hiện có, hoặc integration với Postgres).
- [ ] **Step 2–4:** RED, implement, GREEN (`uv run pytest -q`).
- [ ] **Step 5: Commit** — `git commit -m "feat(account): expose memberships and the SMS switch, grant superadmin from the CLI"`.

---

## Lớp D: chủ sở hữu collection và phạm vi tìm kiếm

### Task D1: Migration 0018, `CollectionTable`, `conversations.collection_ids`

**Files:**
- Modify: `backend/src/pharma_agent/infrastructure/persistence/postgres/corpus_tables.py`, `tables.py` (`ConversationTable.collection_ids`)
- Create: `.../migrations/versions/0018_collection_owners_and_scope.py`
- Modify: `backend/tests/infrastructure/test_migrations.py`

- [ ] **Step 1: Test RED**

```python
async def test_collection_owner_and_visibility_constraints(migrated_dsn: str) -> None:
    engine = create_async_engine(migrated_dsn)
    async with engine.begin() as connection:
        user = await seed_user(
            connection
        )  # helper nhỏ trong file test: INSERT "user" trả id
        org = await seed_org(connection)
        insert = text(
            "INSERT INTO corpus.collections (id, key, title, owner_user_id, owner_organization_id, visibility) VALUES (gen_random_uuid(), :key, 't', :u, :o, :v)"
        )
        await connection.execute(
            insert, {"key": "sys", "u": None, "o": None, "v": "public"}
        )
        await connection.execute(
            insert, {"key": "mine", "u": user, "o": None, "v": "private"}
        )
        await connection.execute(
            insert, {"key": "org", "u": None, "o": org, "v": "organization"}
        )
        for key, u, o, v in [
            ("both", user, org, "private"),
            ("sys-private", None, None, "private"),
            ("user-org", user, None, "organization"),
        ]:
            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await connection.execute(
                        insert, {"key": key, "u": u, "o": o, "v": v}
                    )
    await engine.dispose()
```

Và `_columns(connection, "conversations")` chứa `collection_ids`.

- [ ] **Step 2: RED.**

- [ ] **Step 3: Tables**

`CollectionTable.__table_args__`:

```python
(UniqueConstraint("key", name="uq_collections_key"),)
(
    CheckConstraint(
        "visibility IN ('private', 'organization', 'public')", name="visibility"
    ),
)
(
    CheckConstraint(
        "owner_user_id IS NULL OR owner_organization_id IS NULL", name="one_owner"
    ),
)
(
    CheckConstraint(
        "(owner_user_id IS NULL AND owner_organization_id IS NULL) = (visibility = 'public')"
        " OR owner_user_id IS NOT NULL OR owner_organization_id IS NOT NULL",
        name="system_is_public",
    ),
)
(
    CheckConstraint(
        "visibility <> 'organization' OR owner_organization_id IS NOT NULL",
        name="organization_needs_owner",
    ),
)
(Index("ix_collections_owner_user_id", "owner_user_id"),)
(Index("ix_collections_owner_organization_id", "owner_organization_id"),)
```

Viết lại `system_is_public` cho rõ: `"(owner_user_id IS NOT NULL OR owner_organization_id IS NOT NULL) OR visibility = 'public'"`. Thêm cột `owner_organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)`. `ConversationTable.collection_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(Uuid), nullable=True)`.

- [ ] **Step 4: Migration 0018**: `add_column owner_organization_id`, `drop_constraint ck_collections_visibility` rồi tạo lại với ba giá trị, tạo ba check constraint mới và hai index, `UPDATE corpus.collections SET visibility='public' WHERE owner_user_id IS NULL` (dữ liệu cũ: collection không chủ thành hệ thống công khai, spec 4.10), `add_column conversations.collection_ids ARRAY(Uuid)`. Downgrade ngược (set `visibility='private'` cho hàng `organization` trước khi thu hẹp check).
- [ ] **Step 5: GREEN** — migration tests.
- [ ] **Step 6: Commit** — `git commit -m "feat(db): collections belong to a user, an organization or the system; conversations keep a source scope"`.

### Task D2: `CollectionRepository`, `CollectionService`

**Files:**
- Modify: `backend/src/pharma_agent/domain/corpus/ports.py` (`CollectionRepository`), `domain/corpus/models.py` (`CollectionOwner`)
- Create: `backend/src/pharma_agent/infrastructure/persistence/postgres/collection_repository.py`
- Create: `backend/src/pharma_agent/application/corpus/collections.py`, `errors.py`
- Modify: `backend/src/pharma_agent/infrastructure/persistence/postgres/corpus_repository.py` (`stage_release` không ghi đè owner/visibility; `get_collection` trả owner mới)
- Test: `backend/tests/application/test_collection_service.py`, `backend/tests/infrastructure/test_collection_repository.py`, `backend/tests/corpus_memory.py` (fake `InMemoryCollections`)

**Interfaces (Produces):**

```python
# domain/corpus/models.py
@dataclass(frozen=True) class CollectionOwner: user_id: uuid.UUID | None = None; organization_id: uuid.UUID | None = None
    @classmethod def user(cls, id); def organization(cls, id); SYSTEM = CollectionOwner()
# domain/corpus/ports.py
class CollectionRepository(Protocol):
    async def get(self, collection_id) -> Collection | None
    async def visible_for(self, actor: Actor) -> list[Collection]          # public ∪ own ∪ org theo vai trò (SQL một câu)
    async def list_owned(self, owner: CollectionOwner) -> list[Collection]
    async def count_owned(self, owner) -> int
    async def create(self, collection: Collection, now, tx) -> None
    async def rename(self, collection_id, title, now, tx) -> None
    async def set_visibility(self, collection_id, visibility: Visibility, now, tx) -> None
    async def delete(self, collection_id, tx) -> None                       # cascade releases, chunks; Qdrant xoá ở service
    async def current_releases(self, collection_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]
    async def release_ids(self, collection_id) -> list[uuid.UUID]
# application/corpus/errors.py
class CollectionNotFoundForActor(ApplicationError): code = "COLLECTION_NOT_FOUND"   # 404
class SystemCollectionReadOnly: code = "SYSTEM_COLLECTION_READ_ONLY"               # 403
class QuotaExceeded(InvalidInput): code = "QUOTA_EXCEEDED"; used: int; limit: int   # 422, detail JSON {used, limit, unit}
class PublishInProgress: code = "PUBLISH_IN_PROGRESS"                                 # 409
# application/corpus/collections.py
class CollectionView(BaseModel): id; key; title; visibility; owner_user_id; owner_organization_id; owner_label: str  # "public"|"mine"|org name
                                 is_system: bool; can_edit: bool; can_set_public: bool; current_release_number: int | None; updated_at
class CollectionGroups(BaseModel): public: list[CollectionView]; organizations: list[OrganizationCollections]; mine: list[CollectionView]
class OrganizationCollections(BaseModel): organization_id; name; items: list[CollectionView]
class QuotaUsage(BaseModel): text_used: int; text_limit: int; collections_used: int; collections_limit: int
class QuotaPolicy(frozen): document_chars=200_000; documents_per_collection=100; user_text_bytes=1_000_000; user_collections=5; org_text_bytes=5_000_000; org_collections=20
class CollectionService:
    def __init__(self, *, collections: CollectionRepository, organizations: OrganizationRepository, accounts: AccountRepository,
                 index: VectorIndex, audit: AuditLog, tx: TransactionFactory, clock: Clock, quotas: QuotaPolicy) -> None
    async def visible(self, actor) -> CollectionGroups
    async def get(self, actor, collection_id) -> CollectionView            # 404 nếu không thấy
    async def create(self, actor, *, title, owner: CollectionOwner) -> CollectionView   # quota collections; key sinh "u-"/"o-" + 8 hex; audit
    async def rename(self, actor, collection_id, title) -> CollectionView
    async def set_visibility(self, actor, collection_id, visibility) -> CollectionView  # can_set_visibility else ForbiddenRole; audit với old/new
    async def delete(self, actor, collection_id) -> None                   # xoá điểm Qdrant của mọi release (index.delete theo release_ids rồi chunk ids: dùng repo.release_ids + index_items), rồi repo.delete; audit
    async def quota(self, actor, owner: CollectionOwner) -> QuotaUsage     # text_used tính từ SourceRepository ở E3: ở task này trả 0 cho text_used, limit từ policy/override
```

Việc xoá điểm Qdrant: `CorpusRepository.index_items(release_ids)` trả các `IndexItem` → `index.delete([i.chunk_version_id ...])`. Chunk versions dùng chung giữa collection không xảy ra (id băm theo section key có document key có collection key).

- [ ] **Step 1: Test RED** (fakes): `visible` nhóm đúng ba nhóm cho một actor có 1 org; `create` thứ 6 của người dùng → `QuotaExceeded` với `used=5, limit=5`; `set_visibility` PUBLIC bởi owner → `ForbiddenRole`, bởi superadmin → OK và audit có `details={"from": "private", "to": "public"}`; `rename` collection hệ thống bởi người thường → 404 nếu không thấy (hệ thống luôn public nên thấy) → `SystemCollectionReadOnly`; `delete` xoá điểm Qdrant (fake index ghi lại ids).
- [ ] **Step 2: RED**, **Step 3: Implement** (SQL `visible_for`: `where visibility='public' OR owner_user_id=:u OR (owner_organization_id IN :member_orgs AND visibility='organization') OR owner_organization_id IN :editor_orgs`, superadmin → tất cả), **Step 4: GREEN** unit + `test_collection_repository` integration.
- [ ] **Step 5: Commit** — `git commit -m "feat(corpus): collections owned by users or organizations with visibility rules"`.

### Task D3: Phạm vi tìm kiếm theo quyền trong chat

**Files:**
- Modify: `backend/src/pharma_agent/domain/retrieval/ports.py`, `service.py`, `models.py` (`ReleaseScope`)
- Modify: `backend/src/pharma_agent/infrastructure/retrieval/qdrant_adapter.py` (bỏ `scope` constructor, `search_many(queries, top_k, scope)`), `postgres_corpus.py` (`current_releases(collection_ids)`)
- Create: `backend/src/pharma_agent/application/chat/scope.py`; modify `chat/context.py`, `chat/nodes.py`, `chat/runner.py`, `chat/service.py`
- Create: `backend/src/pharma_agent/infrastructure/retrieval/scope_resolver.py`
- Modify: `backend/src/pharma_agent/infrastructure/composition.py`, `container.py`, `settings.py` (xoá `collections`), `backend/.env.example`, `README.md`
- Test: `backend/tests/domain/test_retrieval_service.py`, `tests/application/test_chat_service.py`, `tests/infrastructure/test_scope_resolver.py`, `tests/infrastructure/test_qdrant_adapter.py`

**Interfaces (Produces):**

```python
# domain/retrieval/models.py
type ReleaseScope = Mapping[UUID, UUID]       # collection_id -> current release_id; rỗng = không có nguồn
# domain/retrieval/ports.py
class Retriever(Protocol):
    async def search_many(self, queries, top_k, *, scope: ReleaseScope) -> list[list[Hit]]
class CorpusReader: async def current_releases(self, collection_ids: Sequence[UUID]) -> dict[UUID, UUID]
# domain/retrieval/service.py
class RetrievalService: async def search(self, queries, rerank_query, known_scores=None, *, scope: ReleaseScope) -> SearchResult
    # scope rỗng -> SearchResult rỗng, không gọi retriever
# application/chat/scope.py
class ScopeResolver(Protocol):
    async def resolve(self, *, user_id: str, requested: Sequence[uuid.UUID] | None) -> ReleaseScope
    # visible ∩ requested (requested None = tất cả), rồi current_releases
# application/chat/context.py: TurnContext thêm scope: ReleaseScope = {}
# application/chat/runner.py: ChatTurnRunner.start(..., scope: ReleaseScope)
# application/chat/service.py: ChatService.__init__(runner, conversations, clock, policy, scopes: ScopeResolver)
#   open_turn(*, user_id, message, conversation_id, collection_ids: Sequence[uuid.UUID] | None = None)
#   -> hội thoại mới: lưu collection_ids vào Conversation; cũ: dùng conversation.collection_ids; scope = scopes.resolve(user_id, ids)
# domain/conversation/models.py: Conversation.collection_ids: tuple[uuid.UUID, ...] | None = None; ConversationRepository.update_scope(conversation)
# infrastructure/retrieval/scope_resolver.py
class PostgresScopeResolver:
    def __init__(self, actors: ActorResolver, collections: CollectionRepository) -> None
    async def resolve(self, *, user_id, requested) -> ReleaseScope
```

`search_node` lấy `runtime.context.scope`; nếu rỗng, không gọi `deps.retrieval.search` và để `run.evidence` rỗng, graph đi tiếp theo nhánh "không có bằng chứng" hiện có (câu trả lời từ chối). `verify_corpus` của retriever đổi thành kiểm tra Qdrant collection và alias (`verify_collection`), không còn kiểm tra danh sách key. Health check `corpus` vẫn báo `CORPUS_NOT_READY` khi alias thiếu hoặc model lệch.

- [ ] **Step 1: Test RED**
  - `test_retrieval_service.py`: `search(..., scope={})` trả rỗng và `FakeRetriever.calls == []`; `scope` được truyền tới retriever.
  - `test_chat_service.py`: `open_turn` với `collection_ids=[c1]` cho hội thoại mới lưu vào conversation và `FakeScopeResolver` nhận `requested=[c1]`; hội thoại cũ dùng ids đã lưu.
  - `test_qdrant_adapter.py`: `search_many(queries, 5, scope={c: r})` dựng filter đúng và không gọi `current_releases`.
  - `test_scope_resolver.py` (integration): A thấy public + của mình; `requested` chứa collection của B → bị loại; collection không có current release → bị loại.
- [ ] **Step 2: RED**, **Step 3: Implement**, cập nhật `tests/fakes.py` `FakeRetriever.search_many(..., scope)`; xoá `PHARMA_RETRIEVAL__COLLECTIONS` khỏi settings, `.env.example`, README, `tests/infrastructure/test_corpus_retrieval_integration.py` (truyền scope trực tiếp).
- [ ] **Step 4: GREEN** — `uv run pytest -q && uv run pytest -q -m integration`.
- [ ] **Step 5: Commit** — `git commit -m "feat(chat): search only the collections the user may see, narrowed per conversation"`.

### Task D4: API collections, phạm vi hội thoại, request chat

**Files:**
- Create: `backend/src/pharma_agent/api/routers/collections.py`
- Modify: `backend/src/pharma_agent/api/routers/conversations.py`, `api/schemas.py` (`ChatRequest.collection_ids`, `UpdateConversationRequest`), `routers/chat.py`, `application/conversation/service.py` (`ConversationView.collection_ids`, `update_scope`), `api/deps.py`, `api/errors.py`, `api/app.py`, `container.py`
- Test: `backend/tests/api/test_collections_api_postgres.py`, `tests/api/test_conversations_api.py`

Routes:

| Method, path | name |
| --- | --- |
| `GET /collections` → `CollectionGroups` | `collections:list` |
| `POST /collections` body `{title, owner_organization_id: uuid | null}` (201) | `collections:create` |
| `GET /collections/{collection_id}` | `collections:get` |
| `PATCH /collections/{collection_id}` body `{title?: str, visibility?: Visibility}` | `collections:update` |
| `DELETE /collections/{collection_id}` (204) | `collections:delete` |
| `GET /collections/quota?organization_id=` → `QuotaUsage` | `collections:quota` |
| `PATCH /conversations/{id}` body `{title?: str, collection_ids?: list[uuid] | null}` | `update_conversation` (thay `renameConversation`; frontend đổi hook ở F1) |

`ChatRequest` thêm `collection_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)`; chỉ áp dụng khi `conversation_id` rỗng, ngược lại bị bỏ qua (ghi trong docstring).

- [ ] **Step 1: Test RED** (`postgres_app` cần `collections`, `actors` trong Container của test: mở rộng `postgres_app` để lắp `build_organization_services` và `build_collection_service`): A tạo collection cá nhân → `GET /collections` của B không thấy; B gọi `GET /collections/{id}` → 404; A `PATCH visibility=public` → 403; `PATCH /conversations/{id}` với `collection_ids=[]` → 422; với `[id]` → view có `collection_ids`.
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** — `git commit -m "feat(api): collection management and per-conversation source scope"`.

### Task D5: Kiểm thử phạm vi trên Qdrant thật

**Files:**
- Create: `backend/tests/infrastructure/test_scope_retrieval_integration.py`

Dựng hai collection với fixture bundle nhỏ (`tests/corpus_fixtures.py`): một của A (private), một của tổ chức O mức `organization`; publish cả hai với `FakeEmbedder`. Dùng `PostgresScopeResolver` thật và `RetrievalService` thật (`build_retrieval_service`).

- [ ] **Step 1: Test** (RED trước khi D3 xong; ở đây phải GREEN):

```python
async def test_users_only_hit_what_they_may_see(platform) -> None:
    a, b, o = await seed_users_and_org(platform)  # b là member của o
    scope_a = await platform.scopes.resolve(user_id=a.hex, requested=None)
    scope_b = await platform.scopes.resolve(user_id=b.hex, requested=None)
    assert set(scope_a) == {platform.private_a}
    assert set(scope_b) == {platform.org_o}
    hits_b = await platform.retrieval.search(
        [Query(text="paracetamol")], "paracetamol", scope=scope_b
    )
    assert {h.collection_id for h in hits_b.hits} == {platform.org_o}


async def test_leaving_the_organization_empties_the_scope_next_turn(platform) -> None:
    a, b, o = await seed_users_and_org(platform)
    await platform.organizations.remove_member(o, b, tx=...)  # qua repo thật
    scope = await platform.scopes.resolve(user_id=b.hex, requested=[platform.org_o])
    assert scope == {}
    result = await platform.retrieval.search([Query(text="x")], "x", scope=scope)
    assert result.hits == []


async def test_narrowing_keeps_only_the_requested_collection(platform) -> None: ...
```

- [ ] **Step 2: Run** — `uv run pytest tests/infrastructure/test_scope_retrieval_integration.py -q -m integration` → PASS.
- [ ] **Step 3: Commit** — `git commit -m "test(retrieval): prove the search scope follows membership and visibility"`.

---

## Lớp E: tự nạp nội dung, job xuất bản, admin

### Task E1: Migration 0019 và domain `source`

**Files:**
- Create: `backend/src/pharma_agent/domain/corpus/source.py`
- Modify: `backend/src/pharma_agent/infrastructure/persistence/postgres/corpus_tables.py`
- Create: `.../migrations/versions/0019_authored_content_and_jobs.py`
- Modify: `backend/tests/infrastructure/test_migrations.py`
- Test: `backend/tests/domain/corpus/test_source.py`

**Interfaces (Produces):**

```python
# domain/corpus/source.py
MAX_DOCUMENT_CHARS = 200_000
class JobStatus(StrEnum): QUEUED="queued"; RUNNING="running"; READY="ready"; FAILED="failed"
class JobStep(StrEnum): BUNDLE="bundle"; CHUNK="chunk"; EMBED="embed"; INDEX="index"; PUBLISH="publish"
@dataclass(frozen=True) class SourceDocument:
    id; collection_id; key: str; title: str; kind: DocumentKind; source_title: str; source_url: str | None
    markdown: str; char_count: int; created_by: uuid.UUID | None; created_at; updated_by: uuid.UUID | None; updated_at
@dataclass(frozen=True) class IngestJob:
    id; collection_id; release_id: uuid.UUID | None; status: JobStatus; step: JobStep; progress: int; error: str | None
    requested_by: uuid.UUID | None; attempts: int; created_at; started_at; finished_at
    def is_open(self) -> bool  # QUEUED or RUNNING
def document_problem(title: str, markdown: str) -> str | None   # tiêu đề 1..200, markdown 1..MAX_DOCUMENT_CHARS
# ports
class SourceRepository(Protocol):
    async def list_documents(self, collection_id) -> list[SourceDocument]
    async def get_document(self, document_id) -> SourceDocument | None
    async def create_document(self, document, tx) -> None     # raise DocumentKeyConflict (DomainError) khi key trùng trong collection
    async def update_document(self, document, tx) -> None
    async def delete_document(self, document_id, tx) -> None
    async def count_documents(self, collection_id) -> int
    async def text_usage(self, owner: CollectionOwner) -> int  # SUM(char_count) qua collections của chủ
    async def glossary(self, collection_id) -> list[GlossaryEntry]
    async def replace_glossary(self, collection_id, entries: Sequence[GlossaryEntry], tx) -> None
    async def colloquial(self, collection_id) -> list[ColloquialMappingRecord]
    async def replace_colloquial(self, collection_id, mappings, tx) -> None
class IngestJobRepository(Protocol):
    async def get(self, job_id) -> IngestJob | None
    async def open_for(self, collection_id) -> IngestJob | None
    async def create(self, job, tx) -> None                      # raise JobConflict khi đã có job mở (unique partial index)
    async def update(self, job, tx) -> None
    async def list_recent(self, *, limit) -> list[IngestJob]
class JobDispatcher(Protocol):
    async def enqueue(self, job_id: uuid.UUID) -> None
```

Bảng (schema `corpus`): `source_documents` (cột như spec 4.7; `UniqueConstraint(collection_id, key)`, `kind` check theo `DocumentKind`, `char_count` Integer), `glossary_entries` (`id`, `collection_id`, `term`, `case_sensitive` Boolean, `vietnamese_expansions ARRAY(Text)`, `english_expansions`, `aliases`, `category` Text default ''; `UniqueConstraint(collection_id, term)`), `colloquial_mappings` (`id`, `collection_id`, `key`, `aliases`, `visual_sign`, `product_names`, `section_keys`; `UniqueConstraint(collection_id, key)`), `ingest_jobs` (cột theo spec; `Index("uq_ingest_jobs_open", "collection_id", unique=True, postgresql_where=text("status IN ('queued','running')"))`, `release_id` FK `corpus.releases.id` `SET NULL`, `requested_by` FK `user.id` `SET NULL`).

- [ ] **Step 1: Test RED**: `EXPECTED_CORPUS_TABLES` thêm bốn bảng; test unique partial index trên `ingest_jobs` (job `ready` cộng job `queued` cùng collection OK; hai `queued` → `IntegrityError`); `test_source.py`: `document_problem`.
- [ ] **Step 2–4:** RED, implement bảng + migration + domain, GREEN.
- [ ] **Step 5: Commit** — `git commit -m "feat(db): authored documents, glossary, colloquial names and ingest jobs"`.

### Task E2: Trình dựng bundle từ Markdown

**Files:**
- Create: `backend/src/pharma_agent/domain/corpus/authoring.py`
- Test: `backend/tests/domain/corpus/test_authoring.py`

**Interfaces (Produces):**

```python
AUTHORING_GENERATOR = BundleGenerator(name="vipharmind-authoring", version="1", build_id="")  # build_id = bundle digest khi dựng
def slugify(text: str, *, max_length: int = 80) -> str                 # bỏ dấu tiếng Việt (unicodedata NFD), chữ thường, [a-z0-9-]
@dataclass(frozen=True) class MarkdownSection: heading: str; path: tuple[str, ...]; ordinal: int; blocks: list[BlockRecord]
def split_markdown(markdown: str, *, fallback_heading: str) -> list[MarkdownSection]
def section_key(document_key: str, path: Sequence[str]) -> str         # f"{document_key}#{'/'.join(slugify(p) for p in path)}" ; path rỗng -> f"{document_key}#body"
def build_bundle(collection: Collection, documents: Sequence[SourceDocument], glossary: Sequence[GlossaryEntry],
                 colloquial: Sequence[ColloquialMappingRecord]) -> KnowledgeBundle
def section_choices(documents) -> list[tuple[str, str]]                # (section_key, "Tài liệu › Mục") cho UI
```

Quy tắc `split_markdown`:
1. Dòng `#`…`######` ngoài fenced code (```` ``` ````) mở mục mới; `path` là ngăn xếp tiêu đề theo cấp (cấp thấp hơn thay thế từ vị trí đó trở đi).
2. Nội dung trước tiêu đề đầu tiên, hoặc toàn tài liệu nếu không có tiêu đề, là mục với `heading=fallback_heading` (tiêu đề tài liệu) và `path=()`.
3. Trong một mục: các dòng liên tiếp bắt đầu bằng `|` tạo block `TABLE` với `table_key=f"t{n}"`; phần còn lại gộp thành block `PROSE`; đoạn trống bị bỏ; mục không còn block nào thì bị bỏ.
4. `SectionRecord.ordinal` tăng từ 1 trong tài liệu; `retrieval=DEFAULT`; không có số trang.
5. `build_bundle`: `DocumentRecord(key=doc.key, kind=doc.kind, title=doc.title, source=SourceInfo(title=doc.source_title, url=doc.source_url))`; sections nối theo thứ tự tài liệu; `manifest.document_count`, `section_count` đúng; `files` để rỗng (manifest chỉ dùng khi ghi ra đĩa, `import_bundle` không đọc `files`); `source_digests={}`; `collection=BundleCollection(key=collection.key, title=collection.title)`; `colloquial_mappings` giữ nguyên `section_keys` nhưng loại key không còn tồn tại (trả về cùng danh sách bị loại qua `build_bundle_report` nếu cần: **không**, UI báo qua `section_choices` ở E3).

- [ ] **Step 1: Test RED**

```python
def test_headings_split_sections_and_tables_become_blocks() -> None:
    md = "Giới thiệu.\n\n# Liều dùng\n\nNgười lớn 500 mg.\n\n| Tuổi | Liều |\n|---|---|\n| <6 | 120 mg |\n\n## Trẻ em\n\nTheo cân nặng.\n\n```\n# not a heading\n```\n"
    sections = split_markdown(md, fallback_heading="Paracetamol")
    assert [s.heading for s in sections] == ["Paracetamol", "Liều dùng", "Trẻ em"]
    assert [s.path for s in sections] == [(), ("Liều dùng",), ("Liều dùng", "Trẻ em")]
    dose = sections[1]
    assert [b.kind for b in dose.blocks] == [BlockKind.PROSE, BlockKind.TABLE]
    assert dose.blocks[1].table_key == "t1" and dose.blocks[1].markdown.startswith(
        "| Tuổi"
    )
    assert (
        sections[2].blocks[0].markdown == "Theo cân nặng.\n\n```\n# not a heading\n```"
    )


def test_a_table_only_document_still_yields_one_section() -> None:  # Review Focus 3
    sections = split_markdown(
        "| a | b |\n|---|---|\n| 1 | 2 |", fallback_heading="Bảng"
    )
    assert len(sections) == 1 and [b.kind for b in sections[0].blocks] == [
        BlockKind.TABLE
    ]


def test_section_keys_are_stable_and_ascii() -> None:
    assert (
        section_key("u-1a2b3c4d-paracetamol", ("Liều dùng", "Trẻ em"))
        == "u-1a2b3c4d-paracetamol#lieu-dung/tre-em"
    )
    assert section_key("d", ()) == "d#body"


def test_build_bundle_digest_is_stable_and_counts_match() -> None:
    bundle = build_bundle(COLLECTION, [DOC], [GLOSSARY], [MAPPING])
    again = build_bundle(COLLECTION, [DOC], [GLOSSARY], [MAPPING])
    assert bundle_digest(bundle) == bundle_digest(again)
    assert bundle.manifest.document_count == 1 and bundle.manifest.section_count == len(
        bundle.sections
    )
    snapshot = build_snapshot(bundle)  # không raise: mọi section trỏ đúng document
    assert snapshot.chunks
```

- [ ] **Step 2–4:** RED, implement, GREEN (`uv run pytest tests/domain/corpus -q`).
- [ ] **Step 5: Commit** — `git commit -m "feat(corpus): build a knowledge bundle from authored Markdown documents"`.

### Task E3: `ContentService`, repository Postgres, hạn mức

**Files:**
- Create: `backend/src/pharma_agent/application/corpus/content.py`
- Create: `backend/src/pharma_agent/infrastructure/persistence/postgres/source_repository.py`, `ingest_job_repository.py`
- Modify: `backend/src/pharma_agent/application/corpus/collections.py` (`quota` dùng `SourceRepository.text_usage`)
- Modify: `backend/tests/corpus_memory.py` (fakes `InMemorySources`, `InMemoryJobs`, `RecordingDispatcher`)
- Test: `backend/tests/application/test_content_service.py`, `backend/tests/infrastructure/test_source_repository.py`

**Interfaces (Produces):**

```python
class DocumentView(BaseModel): id; collection_id; key; title; kind; source_title; source_url; char_count; updated_at; updated_by_name: str
class DocumentDetail(DocumentView): markdown: str
class DocumentInput(BaseModel): title: str; kind: DocumentKind = DRUG_MONOGRAPH; source_title: str = ""; source_url: str | None = None; markdown: str
class SectionChoice(BaseModel): key: str; label: str
class ContentService:
    def __init__(self, *, collections: CollectionRepository, sources: SourceRepository, accounts: AccountRepository,
                 audit: AuditLog, tx: TransactionFactory, clock: Clock, quotas: QuotaPolicy, organizations: OrganizationRepository) -> None
    async def list_documents(self, actor, collection_id) -> list[DocumentView]           # can_view_collection
    async def get_document(self, actor, collection_id, document_id) -> DocumentDetail
    async def create_document(self, actor, collection_id, data: DocumentInput) -> DocumentDetail
        # can_edit_collection (hệ thống -> SystemCollectionReadOnly), document_problem -> InvalidInput,
        # count_documents >= documents_per_collection -> QuotaExceeded(unit="documents"),
        # text_usage(owner) + len(markdown) > text limit -> QuotaExceeded(unit="bytes"); key = slugify(title) (+ "-2", "-3" khi trùng); audit DOCUMENT_CREATED
    async def update_document(self, actor, collection_id, document_id, data) -> DocumentDetail   # quota tính với delta; key giữ nguyên; audit
    async def delete_document(self, actor, collection_id, document_id) -> None
    async def glossary(self, actor, collection_id) -> list[GlossaryEntry]
    async def replace_glossary(self, actor, collection_id, entries) -> list[GlossaryEntry]      # term trùng (case-insensitive) -> InvalidInput; audit
    async def colloquial(self, actor, collection_id) -> list[ColloquialMappingRecord]
    async def replace_colloquial(self, actor, collection_id, mappings) -> list[ColloquialMappingRecord]  # section_keys phải nằm trong section_choices; audit
    async def sections(self, actor, collection_id) -> list[SectionChoice]
    def quota_limits(self, owner, *, user_override, org_override) -> tuple[int, int]            # dùng chung với CollectionService
```

Hạn mức của chủ: `user.text_quota_bytes` / `organizations.text_quota_bytes` ghi đè mặc định; `ContentService` đọc `accounts.get(owner.user_id)` hoặc `organizations.get(owner.organization_id)` để lấy override. Thêm `text_quota_bytes`, `collection_quota` vào `AccountUser` (domain account) và `Organization`.

- [ ] **Step 1: Test RED**: tạo tài liệu bởi editor OK và audit; member → `ForbiddenRole`; người ngoài → `CollectionNotFoundForActor`; tài liệu 200.001 ký tự → `InvalidInput`; tài liệu thứ 101 → `QuotaExceeded(unit="documents")`; vượt byte người dùng với override `text_quota_bytes=10` → `QuotaExceeded(used, limit)`; key tự tăng `-2`; `replace_colloquial` với section key lạ → `InvalidInput`; hệ thống → `SystemCollectionReadOnly`.
- [ ] **Step 2–4:** RED, implement (repository Core SQL với `ARRAY(Text)`), GREEN unit + integration.
- [ ] **Step 5: Commit** — `git commit -m "feat(corpus): author documents, glossary and colloquial names under quotas"`.

### Task E4: Xuất bản qua job, `JobDispatcher`, endpoint nội bộ

**Files:**
- Create: `backend/src/pharma_agent/application/corpus/jobs.py`
- Create: `backend/src/pharma_agent/infrastructure/jobs/__init__.py`, `inprocess.py`, `cloud_tasks.py`, `internal_auth.py`
- Modify: `backend/src/pharma_agent/infrastructure/settings.py` (`JobsSettings`, `QuotaSettings`), `container.py`, `corpus_factory.py`
- Create: `backend/src/pharma_agent/api/routers/internal.py`; modify `api/deps.py`, `api/app.py`
- Modify: `backend/pyproject.toml` (`google-cloud-tasks>=2.19,<3`, `google-auth>=2.40,<3`, `python-multipart>=0.0.20`)
- Test: `backend/tests/application/test_publish_service.py`, `backend/tests/infrastructure/test_internal_auth.py`, `backend/tests/api/test_internal_api_postgres.py`

**Interfaces (Produces):**

```python
# settings
class JobsSettings(BaseModel):
    dispatcher: Literal["inprocess", "cloud_tasks"] = "inprocess"
    internal_token: SecretStr | None = None            # inprocess: header X-Internal-Token
    backend_url: str | None = None                     # https://...run.app ; audience OIDC và URL target
    cloud_tasks_project: str | None = None; cloud_tasks_location: str = "asia-southeast1"; cloud_tasks_queue: str = "ingest"
    service_account_email: str | None = None           # invoker; email trong OIDC token phải trùng
    max_attempts: int = 3
class QuotaSettings(BaseModel): document_chars=200_000; documents_per_collection=100; user_text_bytes=1_000_000; user_collections=5; org_text_bytes=5_000_000; org_collections=20
Settings.jobs: JobsSettings; Settings.quotas: QuotaSettings
# application/corpus/jobs.py
class JobView(BaseModel): id; collection_id; status; step; progress; error; release_number: int | None; created_at; started_at; finished_at
class PublishService:
    def __init__(self, *, collections, sources, jobs: IngestJobRepository, releases: CorpusRepository, importer: ImportKnowledgeBundle,
                 corpus: CorpusService, dispatcher: JobDispatcher, audit, tx, clock, max_attempts: int) -> None
    async def publish(self, actor, collection_id) -> JobView          # can_edit; không có tài liệu -> InvalidInput("nothing to publish"); open_for -> PublishInProgress; tạo job QUEUED rồi dispatcher.enqueue(job.id) SAU commit
    async def get_job(self, actor, job_id) -> JobView                 # can_view_collection của job.collection_id
    async def run(self, job_id) -> JobView                            # gọi bởi endpoint nội bộ
    async def rollback(self, actor, collection_id) -> CollectionView  # corpus.rollback(collection.key); audit COLLECTION_ROLLED_BACK
```

`run(job_id)`:
1. `job = jobs.get(id)`; không có → `InvalidInput`. Nếu `status in (READY, FAILED)` → trả view không làm gì (Review Focus 5).
2. Đặt `RUNNING`, `attempts += 1`, `started_at`, `step=BUNDLE` (commit riêng).
3. `bundle = build_bundle(collection, documents, glossary, colloquial)`; `step=CHUNK`→`EMBED`→`INDEX` cập nhật qua callback `on_step` của `ImportKnowledgeBundle` (thêm tham số `progress: Callable[[JobStep, int], Awaitable[None]] | None = None` vào `__call__`, gọi sau `stage_release`, trước/giữa các lô ghi, trước `publish`).
4. `report = importer(bundle, embeddings=lambda *_: {}, publish=True)`; `step=PUBLISH`; `release_id=report.release.id`; `status=READY`, `progress=100`, `finished_at`; audit `COLLECTION_PUBLISHED` với `details={"release": report.release.number, "outcome": report.outcome}`.
5. Lỗi: nếu `attempts < max_attempts` → `status=QUEUED`, `error=str(exc)[:500]`, re-raise để Cloud Tasks gọi lại (endpoint trả 500); ngược lại `status=FAILED`, trả view (200). Với `InProcessDispatcher`, lỗi được log và không re-raise ra ngoài task.

`InProcessDispatcher(run: Callable[[uuid.UUID], Awaitable[object]])`: `enqueue` tạo `asyncio.create_task` và giữ tham chiếu trong set để không bị GC; có `await drain()` cho test và e2e. `CloudTasksDispatcher(settings: JobsSettings)`: `tasks_v2.CloudTasksAsyncClient().create_task(parent=queue_path, task={"http_request": {"http_method": POST, "url": f"{backend_url}/api/v1/internal/ingest-jobs/{job_id}/run", "oidc_token": {"service_account_email": ..., "audience": backend_url}}})`, `dispatch_deadline` 600 giây. `internal_auth.verify_internal_request(request, settings) -> None`: inprocess → so `X-Internal-Token` bằng `hmac.compare_digest`; cloud_tasks → `google.oauth2.id_token.verify_oauth2_token(bearer, Request(), audience=backend_url)` và `claims["email"] == service_account_email`; sai → `HTTPException(401)`.

Route: `POST /internal/ingest-jobs/{job_id}/run` name `internal:ingest_jobs.run`, `include_in_schema=False`, dependency `verify_internal`. Container: `publish: PublishService`, `content: ContentService`, `dispatcher`. Khi `dispatcher == "inprocess"`, container tạo `InProcessDispatcher(container.publish.run)`.

- [ ] **Step 1: Test RED**
  - `test_publish_service.py`: publish tạo job và `RecordingDispatcher.enqueued == [job.id]`; publish lần hai khi job mở → `PublishInProgress`; hai `publish` song song qua `asyncio.gather` với fake repo mô phỏng unique index → đúng một job (Review Focus 2); `run` chạy importer giả, các bước đi `BUNDLE→…→PUBLISH`, `READY`, audit; `run` khi `READY` không gọi importer (Review Focus 5); lỗi lần 1 → `QUEUED` và re-raise, lần `max_attempts` → `FAILED`.
  - `test_internal_auth.py`: inprocess token sai → 401; đúng → qua.
  - `test_internal_api_postgres.py`: `POST /internal/...` không token → 401; có token với job không tồn tại → 422.
- [ ] **Step 2–4:** RED, implement, GREEN (`uv run pytest -q && uv run pytest -q -m integration`). Chạy `uv lock` sau khi thêm dependency; pre-commit `uv-lock` kiểm tra.
- [ ] **Step 5: Commit** — `git commit -m "feat(corpus): publish authored collections through a background job"`.

### Task E5: API tài liệu, metadata, job, tải lên

**Files:**
- Create: `backend/src/pharma_agent/api/routers/documents.py`, `jobs.py`
- Modify: `backend/src/pharma_agent/api/routers/collections.py` (`publish`, `rollback`, `releases`)
- Test: `backend/tests/api/test_documents_api_postgres.py`

Routes:

| Method, path | name |
| --- | --- |
| `GET /collections/{collection_id}/documents` | `documents:list` |
| `POST /collections/{collection_id}/documents` (201) → `DocumentDetail` | `documents:create` |
| `POST /collections/{collection_id}/documents/upload` multipart `file` → `{title, markdown, char_count}` (không lưu) | `documents:upload` |
| `GET/PATCH/DELETE /collections/{collection_id}/documents/{document_id}` | `documents:get/update/delete` |
| `GET/PUT /collections/{collection_id}/glossary` | `collections:glossary.get/put` |
| `GET/PUT /collections/{collection_id}/colloquial` | `collections:colloquial.get/put` |
| `GET /collections/{collection_id}/sections` | `collections:sections` |
| `GET /collections/{collection_id}/releases` → `list[ReleaseSummary]`-like view | `collections:releases` |
| `POST /collections/{collection_id}/publish` (202) → `JobView` | `collections:publish` |
| `POST /collections/{collection_id}/rollback` → `CollectionView` | `collections:rollback` |
| `GET /ingest-jobs/{job_id}` | `jobs:get` |

Upload: chấp nhận `text/plain`, `text/markdown` hoặc tên `.txt`/`.md`, tối đa 1 MB (`PayloadTooLarge`), decode UTF-8 (lỗi → `InvalidInput("the file is not UTF-8 text")`); `.txt` giữ nguyên nội dung; `title` lấy từ dòng `# ` đầu tiên của `.md` hoặc tên file không đuôi.

- [ ] **Step 1: Test RED**: editor tạo tài liệu qua API, `GET` trả markdown; `upload` một file `.md` trả title từ `#`; `PUT glossary` với term trùng → 422; `publish` → 202 với `status=queued`; với `InProcessDispatcher` trong `postgres_app` (dùng `FakeEmbedder` và Qdrant thật qua fixture `qdrant_url`) chờ `drain()` rồi `GET /ingest-jobs/{id}` → `ready`, `GET /collections/{id}` có `current_release_number == 1`; `publish` lần hai khi không đổi → job `ready` với `outcome=no_change`.
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** — `git commit -m "feat(api): author, upload and publish collection content"`.

### Task E6: `AdminService` và API admin

**Files:**
- Create: `backend/src/pharma_agent/application/admin/__init__.py`, `service.py`
- Create: `backend/src/pharma_agent/api/routers/admin.py`
- Modify: `backend/src/pharma_agent/domain/account/ports.py` (`AccountRepository.search(query, *, limit, cursor) -> list[AccountUser]`, `set_active`, `set_quotas`), `domain/conversation/ports.py` (`ConversationRepository.list_for_user` đã có; thêm `get_any(conversation_id)` cho admin), `application/account/service.py`, `infrastructure/...`
- Test: `backend/tests/application/test_admin_service.py`, `backend/tests/api/test_admin_api_postgres.py`

**Interfaces (Produces):**

```python
class AdminUserView(BaseModel): id; email; phone_number; display_name; is_active; is_superadmin; created_at; text_quota_bytes; collection_quota; organizations: list[MembershipView]
class AdminService:
    def __init__(self, *, accounts, organizations, collections, jobs, conversations: ConversationRepository, sessions: SessionStore, audit, tx, clock) -> None
    async def users(self, actor, *, query: str | None, limit, cursor) -> Page[AdminUserView]
    async def set_user_active(self, actor, user_id, active: bool) -> AdminUserView      # tắt -> sessions.delete_all(user_id); audit USER_DISABLED/ENABLED subject_user_id
    async def set_user_quotas(self, actor, user_id, *, text_quota_bytes, collection_quota) -> AdminUserView   # audit QUOTA_CHANGED
    async def organizations(self, actor, *, limit, cursor) -> Page[OrganizationView]
    async def set_organization_quotas(self, actor, organization_id, *, text_quota_bytes, collection_quota) -> OrganizationView
    async def collections(self, actor, *, limit, cursor) -> Page[AdminCollectionView]   # CollectionView + qdrant_points (VectorIndex.count_release của release hiện hành) + text_used
    async def jobs(self, actor, *, limit) -> list[JobView]
    async def user_conversations(self, actor, user_id, *, limit, cursor) -> ConversationPage
    async def conversation_messages(self, actor, conversation_id, *, limit, cursor) -> MessagePage   # không ghi nhật ký
```

Mọi phương thức bắt đầu bằng `if not actor.is_superadmin: raise ForbiddenRole`. Routes dưới `/admin/...` theo spec mục 7 với name `admin:users.list`, `admin:users.update`, `admin:organizations.list`, `admin:organizations.update`, `admin:collections.list`, `admin:ingest_jobs.list`, `admin:users.conversations`, `admin:conversations.messages`, `admin:audit` (dùng `AuditService.everything`). Người không phải superadmin nhận **404** ở mọi route admin (không phải 403), để không lộ trang admin: router admin dùng dependency `require_superadmin` raise `HTTPException(404)`.

- [ ] **Step 1: Test RED**: người thường gọi `GET /admin/users` → 404; superadmin (set bằng `UPDATE "user" SET is_superuser=true` trong test) → 200; khoá user → phiên của user đó mất (`GET /users/me` của họ → 401); audit có `user.disabled`; đọc tin nhắn hội thoại người khác → 200 và `GET /admin/audit` **không** có sự kiện mới.
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** — `git commit -m "feat(admin): superadmin reads and manages users, organizations, collections and jobs"`.

### Task E7: Reranker DeepInfra và SMS `none`

**Files:**
- Create: `backend/src/pharma_agent/infrastructure/retrieval/deepinfra_reranker.py`
- Modify: `backend/src/pharma_agent/infrastructure/retrieval/llama_cpp_reranker.py` (`build_reranker`), `settings.py` (`RerankSettings.protocol: Literal["native_rerank", "deepinfra", "none"]`, `SmsSettings.provider: Literal["log", "none"]`), `notifications/factory.py`, `backend/.env.example`, `backend/README.md`
- Test: `backend/tests/infrastructure/test_deepinfra_reranker.py` (respx), `tests/infrastructure/test_notifications.py`

```python
class DeepInfraReranker:
    def __init__(self, http: httpx.AsyncClient, *, model: str, max_concurrent: int = 2) -> None
    async def rerank(self, query, hits, top_n) -> list[Hit]:
        # POST f"/v1/inference/{model}" json={"queries": [query] * len(hits), "documents": [_document_text(h) ...]}
        # payload["scores"][i] là điểm của hits[i]; thiếu/khác độ dài -> RetrievalError
```

`build_reranker`: `protocol == "deepinfra"` → `httpx.AsyncClient(base_url=settings.base_url, headers={"Authorization": f"bearer {api_key}"}, timeout=...)` và `DeepInfraReranker`. `build_sms_sender`: `provider == "none"` → `LogSmsSender` vẫn được trả nhưng `AccountPolicy.sms_enabled=False` (C5) chặn trước khi gửi.

- [ ] **Step 1: Test RED** (respx mock `https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Reranker-4B` trả `{"scores":[0.1,0.9]}` → thứ tự đảo; `scores` thiếu → `RetrievalError`).
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** — `git commit -m "feat(retrieval): rerank through DeepInfra's inference endpoint"`.

---

## Lớp F: frontend

### Task F1: Sinh lại client, i18n, luật kiến trúc, điều hướng, ẩn SMS

**Files:**
- Regenerate: `frontend/openapi.json`, `frontend/app/api/gen/**` (`npm run api:openapi && npm run api:generate`)
- Create: `frontend/app/i18n/resources/{vi,en}/{organizations,collections,admin,audit,legal}.json`; modify `app/i18n/config.ts`, `resources/{vi,en}/common.json` (nav), `errors.json` (mã lỗi mới)
- Modify: `frontend/app/architecture.test.ts` (`ALLOWED_FEATURE_IMPORTS`), `.oxlintrc.json`, `frontend/README.md`
- Modify: `frontend/app/features/shell/components/AppSidebar.tsx` (ghép từ block `dashboard-01`: `app-sidebar` + `nav-main` + `nav-secondary` + `nav-user` với `avatar`; danh sách hội thoại trong `SidebarContent`; đầu trang là `site-header` của block), `app/routes/auth/login.tsx`, `register.tsx`, `features/settings/components/AccountSection.tsx` (ẩn SĐT khi `phone_sign_in_enabled === false`), `tests/utils/account.ts` (`accountView` thêm `is_superadmin: false`, `memberships: []`, `phone_sign_in_enabled: true`)
- Modify: `frontend/app/features/conversations/components/RenameConversationDialog.tsx` (hook đổi tên `useUpdateConversation`, body `{title}`)

`ALLOWED_FEATURE_IMPORTS` mới:

```ts
const ALLOWED_FEATURE_IMPORTS: Record<string, string[]> = {
  chat: ["conversations"],
  shell: ["auth", "conversations"],
  organizations: ["audit", "collections"],
  admin: ["chat", "audit"],
  settings: ["audit"],
}
```

`.oxlintrc.json`: thêm override cho `organizations`, `collections`, `audit`, `admin`, `legal`; cập nhật danh sách cấm của mọi feature cũ với năm feature mới (trừ hướng được phép). Test "the oxlint boundary rules match" bắt lỗi nếu thiếu.

`NAV_ITEMS`: Chat, Tổ chức (`/organizations`), Collection (`/collections`), Hoạt động (`/activity`), Cài đặt; mục Quản trị (`/admin`) chỉ khi `user.is_superadmin`. Khoá `common.nav.organizations|collections|activity|admin`.

Mã lỗi mới trong `errors.json`: `FORBIDDEN_ROLE`, `ORGANIZATION_NOT_FOUND`, `LAST_OWNER`, `ALREADY_MEMBER`, `MEMBER_NOT_FOUND`, `INVITATION_NOT_FOUND`, `INVITATION_EXPIRED`, `INVITATION_NOT_PENDING`, `INVITATION_EMAIL_MISMATCH`, `INVITATION_ALREADY_OPEN`, `ORGANIZATION_NAME_INVALID`, `COLLECTION_NOT_FOUND`, `SYSTEM_COLLECTION_READ_ONLY`, `QUOTA_EXCEEDED`, `PUBLISH_IN_PROGRESS`, `PHONE_SIGN_IN_DISABLED`.

- [ ] **Step 1:** Sinh client; `npm run typecheck` sẽ FAIL ở `RenameConversationDialog` (hook đổi tên) và nơi dùng `accountView` → sửa.
- [ ] **Step 2: Test RED**: `AppSidebar.browser.test.tsx` thêm ca "ẩn Quản trị với người thường, hiện với superadmin". Trang đăng nhập và đăng ký chưa có người dùng, nên cờ SMS lấy từ `GET /api/v1/health`: backend thêm trường `phone_sign_in_enabled: bool` vào `HealthResponse` (một dòng, kèm test ở `tests/api/test_health_api.py`), frontend đọc qua `useHealth()`; test stub health trả `false` → không có tab "Số điện thoại".
- [ ] **Step 3:** Implement; `npx vitest run app/architecture.test.ts app/features/shell app/features/auth` → PASS.
- [ ] **Step 4:** `npm run lint && npm run typecheck && npx vitest run` → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(frontend): regenerate the client, add navigation and boundaries for the new features"`.

### Task F2: Primitive shadcn còn thiếu

- [x] **Step 1:** `cd frontend && npx shadcn@latest add popover checkbox table progress native-select hover-card item toggle toggle-group button-group combobox` (style `base-nova` theo `components.json`), rồi `npx shadcn@latest add dashboard-01` để lấy block (`app-sidebar`, `nav-*`, `site-header`, `section-cards`, `data-table`, `avatar`, `breadcrumb`). Giữ bản local của file `ui` đã sửa vì lint. Bỏ demo `app/routes/dashboard.tsx`, `app/dashboard/data.json`, `chart-area-interactive`, `nav-documents`, `sonner`, `next-themes`, `@dnd-kit`, `recharts`; ghim phiên bản các gói còn lại.
- [ ] **Step 2:** `npm run lint && npm run typecheck` → PASS.
- [ ] **Step 3: Commit** — `git commit -m "chore(ui): add popover, checkbox, table and progress primitives"`.

### Task F3: Feature `audit`

**Files:**
- Create: `frontend/app/features/audit/components/AuditList.tsx` (`item` cho mỗi sự kiện, `empty` khi rỗng, `alert` khi lỗi), `AuditList.browser.test.tsx`, `features/audit/lib/describe-event.ts`, `describe-event.test.ts`
- Create: `frontend/app/routes/app/activity.tsx`; modify `app/routes.ts`

```ts
// features/audit/lib/describe-event.ts
export function describeEvent(event: AuditEventView, t: TFunction<"audit">): string
// khoá audit.json: "action.organization.created": "{{actor}} đã tạo tổ chức {{name}}", ... mỗi AuditAction một khoá; actor = event.actor_name, kèm hậu tố " (Quản trị viên)" khi actor_was_superadmin
// AuditList({ fetchPage }: { fetchPage: (cursor?: string) => Promise<AuditPage> }) dùng useInfiniteQuery với queryKey truyền vào; hiện thời gian bằng Intl.DateTimeFormat
```

`AuditList` nhận `queryKey` và `queryFn` để dùng chung cho tổ chức, cá nhân và admin. Route `/activity` gọi `useAuditMineInfinite`.

- [ ] **Step 1: Test RED** (`describe-event.test.ts`: mỗi action có khoá ở cả vi và en, không còn `{{` sau khi dịch với details mẫu; `AuditList` hiển thị câu và tải trang 2 khi cuộn).
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** — `git commit -m "feat(frontend): audit log list and the activity page"`.

### Task F4: Feature `organizations`

**Files:**
- Create: `frontend/app/features/organizations/components/{OrganizationsPage,CreateOrganizationDialog,OrganizationPage,MembersTab,InvitationsTab,InviteDialog,OrgCollectionsTab,DeleteOrganizationDialog}.tsx` + `.browser.test.tsx` cho `OrganizationPage`, `MembersTab`, `InvitationsTab`
- Create: `frontend/app/routes/app/organizations.tsx`, `organization.tsx`; modify `app/routes.ts` (`route("organizations", ...)`, `route("organizations/:organizationId/:tab?", ...)`)

Hành vi:
- `OrganizationsPage`: danh sách `useOrganizationsList` bằng `item`, form tạo tổ chức là `NameForm` dùng chung (react-hook-form + zod + `field`, `app/components/name-form.tsx`).
- `OrganizationPage`: tiêu đề, vai trò của tôi, `Tabs` với giá trị từ `:tab` (mặc định `members`); tab `invitations` hiện với mọi thành viên (member chỉ thấy lời mời của mình, server lọc); tab `collections` hiện với mọi thành viên; tab `audit` chỉ `owner`/`editor`; nút Đổi tên và Xoá chỉ `owner`; nút Rời tổ chức cho mọi người (disabled kèm tooltip khi là owner cuối, server trả `LAST_OWNER` → toast).
- `MembersTab`: `Table` tên, email, vai trò (`native-select` đổi vai trò nếu owner), nút Xoá (AlertDialog).
- `InvitationsTab`: danh sách `item` email, vai trò, trạng thái (Badge), người mời, hạn; form Mời inline bằng react-hook-form + zod (`InvitationsCreateBody`) với email + `native-select` vai trò chỉ gồm các vai trò được phép theo vai trò của tôi; với trạng thái `pending_approval` và tôi là owner/editor: nút Duyệt, Từ chối; `sent`: Gửi lại, Thu hồi; member thấy nút Thu hồi cho lời mời của mình.
- `OrgCollectionsTab`: lọc `CollectionGroups.organizations[organization_id]` và nút Tạo collection cho tổ chức (dùng component `CreateCollectionDialog` của feature `collections`, owner cố định).
- `DeleteOrganizationDialog`: ô nhập tên, nút Xoá disabled tới khi khớp.

- [ ] **Step 1: Test RED** (MSW): `OrganizationPage` với `/users/me` role member → không có tab Nhật ký, không có nút Đổi tên; `InvitationsTab`: member mời → body `{email, role: "member"}` và hàng mới hiện "Chờ duyệt"; owner bấm Duyệt → POST `.../approve`; `MembersTab`: owner đổi vai trò → PATCH body `{role}`.
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** — `git commit -m "feat(frontend): organizations with members, invitations and audit"`.

### Task F5: Trang nhận lời mời

**Files:**
- Create: `frontend/app/routes/public/invitation.tsx`; `frontend/app/features/organizations/components/InvitationLanding.tsx` + test
- Modify: `app/routes.ts` (`route("invitations/:token", "routes/public/invitation.tsx")`), `app/features/auth/lib/next-path.ts` nếu cần cho phép `/invitations/...`

Hành vi: `useInvitationsPreview(token)` công khai → hiện tổ chức, người mời, vai trò, `email_hint`. Trạng thái người dùng lấy từ `currentUserQueryOptions()` với `retry: false`: chưa đăng nhập (401) → hai nút Đăng nhập, Đăng ký với `next=/invitations/{token}`; đã đăng nhập → nút Tham gia (POST accept → toast và `navigate(/organizations/{id})`) và Từ chối; lỗi `INVITATION_EMAIL_MISMATCH` → câu "Lời mời này dành cho {{hint}}, bạn đang đăng nhập bằng {{email}}" và nút Đăng xuất; 404 → "Lời mời không còn hiệu lực".

- [ ] **Step 1–5:** RED (3 ca: chưa đăng nhập; chấp nhận; sai email), implement, GREEN, commit `feat(frontend): invitation landing page`.

### Task F6: Feature `collections` (danh sách, chi tiết, metadata, release)

**Files:**
- Create: `frontend/app/features/collections/components/{CollectionsPage,QuotaBar,CreateCollectionDialog,CollectionPage,DocumentsTab,GlossaryTab,ColloquialTab,ReleasesTab,VisibilitySelect,PublishButton,JobProgress}.tsx` + tests cho `CollectionPage`, `GlossaryTab`, `PublishButton`
- Create: `frontend/app/features/collections/lib/{quota,section-label}.ts`
- Create: `frontend/app/routes/app/collections.tsx`, `collection.tsx`; modify `app/routes.ts`

Hành vi:
- `CollectionsPage`: ba nhóm theo `CollectionGroups`; `QuotaBar` (Progress) cho "Của tôi" và mỗi tổ chức từ `useCollectionsQuota`; nút Tạo collection (chọn chủ: tôi hoặc tổ chức tôi là editor/owner).
- `CollectionPage`: tiêu đề (đổi tên inline nếu `can_edit`), `VisibilitySelect` (Riêng tư / Trong tổ chức khi chủ là tổ chức / Công khai chỉ khi `can_set_public`), tabs `documents | glossary | colloquial | releases`; collection hệ thống: chỉ tab releases, mọi nút ẩn, nhãn "Hệ thống".
- `DocumentsTab`: bảng tiêu đề, loại, số ký tự, cập nhật; nút Thêm tài liệu → `/collections/:id/documents/new`; hàng bấm mở `/collections/:id/documents/:docId`; Xoá với AlertDialog.
- `GlossaryTab`: mỗi mục một `item` có ô term và phân loại (`input`), còn mở rộng tiếng Việt, tiếng Anh, tên khác là `TagsInput` (`app/components/tags-input.tsx`, ghép từ `combobox` chip: gõ rồi Enter thành chip); nút Lưu gửi `PUT` cả danh sách. `ColloquialTab` tương tự, mục liên quan chọn bằng `SectionPicker` (`combobox` nhiều lựa chọn có ô tìm).
- `ColloquialTab`: tương tự; cột "Mục" là multi-select từ `useCollectionsSections`; key không còn tồn tại hiện Badge cảnh báo.
- `ReleasesTab`: danh sách `item` số, ngày, Badge "Đang dùng"; nút Quay lại bản trước. `CollectionsPage` nhóm bằng `item`, hạn mức bằng `progress`, tạo bằng `NameForm`.
- `PublishButton` + `JobProgress`: POST publish → lưu `job.id` trong state, poll `useJobsGet(jobId, { query: { refetchInterval: (q) => q.state.data?.status in ["queued","running"] ? 2000 : false } })`; hiện bước bằng Progress và nhãn `collections.job.step.{bundle|chunk|embed|index|publish}`; xong thì invalidate collection và releases; lỗi hiện `error`; `PUBLISH_IN_PROGRESS` → toast.

- [ ] **Step 1: Test RED**: `CollectionPage` ẩn Công khai cho người thường, hiện cho superadmin; hệ thống chỉ có tab Bản phát hành; `GlossaryTab` PUT đúng body sau khi thêm dòng; `PublishButton` poll hai lần rồi hiện "Hoàn tất".
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** — `git commit -m "feat(frontend): collections with quotas, metadata tabs, releases and publishing"`.

### Task F7: Trình soạn tài liệu Tiptap và tải lên

**Files:**
- `npm install @tiptap/react @tiptap/starter-kit @tiptap/markdown @tiptap/extension-table` (bản 3.x mới nhất, ghim đúng phiên bản như các gói khác)
- Create: `frontend/app/features/collections/components/{DocumentEditorPage,MarkdownEditor,EditorToolbar,UploadButton}.tsx`, `MarkdownEditor.browser.test.tsx`, `DocumentEditorPage.browser.test.tsx`; `features/collections/lib/document-schema.ts`
- Create: `frontend/app/routes/app/document.tsx` (`collections/:collectionId/documents/:documentId`, với `documentId === "new"` là tạo mới); modify `app/routes.ts`
- Modify: `frontend/app/api/upload.ts` (mới): `uploadDocumentFile(collectionId, file): Promise<UploadResult>` dùng `fetch` multipart với CSRF header (fetcher hiện tại không gửi FormData)

`MarkdownEditor({ value, onChange, id })`: `useEditor({ extensions: [StarterKit, Markdown, TableKit.configure({ table: { resizable: false } })], content: value, contentType: "markdown", onUpdate: ({ editor }) => onChange(editor.getMarkdown()) })`; toolbar là `toggle` cho H1–H3, đậm, nghiêng, danh sách và `button-group` cho chèn bảng 3×3, thêm hàng, xoá bảng, mỗi nút có `tooltip`; vùng soạn dùng `prose` của `@tailwindcss/typography`. Vùng soạn có `role="textbox"` và `aria-labelledby` nhãn "Nội dung". SSR: component chỉ render editor sau `useEffect` mount (Tiptap cần DOM); trước đó hiện `Skeleton`.

`DocumentEditorPage`: form tiêu đề, loại (Select theo `DocumentKind`), nguồn, URL nguồn, nội dung (MarkdownEditor), đếm ký tự `/ 200.000`, nút Lưu; `UploadButton` nhận `.txt,.md`, gọi `uploadDocumentFile`, đổ `title` và `markdown` vào form (ghi đè sau khi confirm nếu form đã có nội dung). Lỗi `QUOTA_EXCEEDED` hiện câu với `used/limit`.

- [ ] **Step 1: Test RED**: gõ `# Tiêu đề` + Enter + "Nội dung" trong editor → `onChange` cuối cùng là `"# Tiêu đề\n\nNội dung"`; chèn bảng → markdown có `|`; `DocumentEditorPage` lưu → POST body đúng; upload file `.md` giả → form điền tiêu đề.
- [ ] **Step 2–4:** RED, implement, GREEN (`npx vitest run app/features/collections`).
- [ ] **Step 5: Commit** — `git commit -m "feat(frontend): write documents in a Tiptap editor or upload Markdown"`.

### Task F8: Nút Nguồn trong chat

**Files:**
- Create: `frontend/app/features/chat/components/SourcesPopover.tsx` + `.browser.test.tsx`; `features/chat/lib/sources-scope.ts`
- Modify: `Composer.tsx` (prop `leading?: ReactNode` để đặt nút trước ô nhập), `ChatSession.tsx`, `NewChat.tsx`, `lib/chat-transport.ts` (`prepareSendMessagesRequest` thêm `collection_ids` từ `body` option khi hội thoại mới), `features/conversations/lib/conversation-cache.ts`

Hành vi: `SourcesPopover({ value: string[] | null, onChange })` là `combobox` nhiều lựa chọn (`ComboboxTrigger` là `Button`, popup có `ComboboxInput` tìm, nút "Tất cả nguồn tôi được thấy" đặt value null, `ComboboxGroup` theo Công khai / từng tổ chức / Của tôi). Nút hiện "Nguồn" hoặc "Nguồn: N". Danh sách bộ tài liệu chỉ tải khi mở. Lựa chọn hiện ngay rồi mới PATCH (optimistic). Hội thoại có sẵn: `value` từ `conversation.collection_ids`, `onChange` gọi `useUpdateConversation` `{collection_ids}` và cập nhật cache. Hội thoại mới (`NewChat`): giữ lựa chọn trong state; khi gửi câu đầu, `createConversation` → nếu có lựa chọn thì `updateConversation({collection_ids})` → navigate kèm câu hỏi như hiện nay. Vì vậy `ChatRequest.collection_ids` ở backend chỉ dùng cho client API, giao diện không cần gửi nó.

- [ ] **Step 1: Test RED**: popover hiện ba nhóm; bỏ chọn tất cả rồi tick một collection → PATCH `{collection_ids: [id]}` và nút hiện "Nguồn: 1"; tick lại "Tất cả" → PATCH `{collection_ids: null}`.
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** — `git commit -m "feat(chat): narrow a conversation to chosen sources"`.

### Task F9: Feature `admin`

**Files:**
- Create: `frontend/app/features/admin/components/{AdminPage,AdminOverview,UsersSection,QuotaDialog,QuotaValue,UserConversationsSheet,ReadOnlyThread,OrganizationsSection,CollectionsSection,JobsSection}.tsx` + tests cho `AdminPage`, `ReadOnlyThread`; `features/admin/lib/require-superadmin.ts`. Toàn trang ghép từ block `dashboard-01` đã cài ở F2: `site-header` (tiêu đề "Quản trị"), `section-cards` đổ số từ `useAdminCollectionsList` và `useAdminIngestJobsList` (bộ tài liệu, tài liệu, điểm vector, tác vụ lỗi), `data-table` của block cho bốn bảng (truyền cột; ô tìm người dùng đặt ở toolbar của bảng, nút Tải thêm ở footer). Không tự viết lại `DataTable`.
- Create: `frontend/app/routes/app/admin.tsx` (`admin/:section?`), modify `app/routes.ts`

Guard: `clientLoader` của route admin gọi `requireUser` rồi nếu `!user.is_superadmin` → `throw data(null, { status: 404 })` để `ErrorBoundary` hiện trang 404 hiện có. `AdminPage`: `site-header` + `section-cards` + Tabs Người dùng / Tổ chức / Collection / Job / Nhật ký. `UsersSection`: `data-table` của block với ô tìm trong toolbar, nút Khoá/Mở (AlertDialog), Hạn mức (`QuotaDialog`, react-hook-form + zod), Hội thoại (Sheet liệt kê `useAdminUsersConversationsInfinite`, bấm mở `ReadOnlyThread`). `ReadOnlyThread` dùng `MessageParts` của chat với `renderActions` bỏ trống, `useAdminConversationsMessagesInfinite`. `AuditSection` dùng `AuditList` với `useAdminAuditInfinite`.

- [ ] **Step 1: Test RED**: người thường vào `/admin` thấy trang 404 (dùng `createRoutesStub` với loader); superadmin khoá người dùng → PATCH `{is_active:false}`; `ReadOnlyThread` render tin nhắn không có nút phản hồi.
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** — `git commit -m "feat(frontend): superadmin console"`.

### Task F10: Trang pháp lý và footer

**Files:**
- Create: `frontend/app/features/legal/components/{LegalPage,SiteFooter}.tsx`, `features/legal/lib/content.ts` (nội dung hai ngôn ngữ theo spec 9.3 mục 4, dạng mảng section `{heading, paragraphs[]}`), test cho `LegalPage`
- Create: `frontend/app/routes/public/privacy.tsx`, `terms.tsx`; modify `app/routes.ts`, `react-router.config.ts` (`prerender: ["/", "/en", "/privacy", "/en/privacy", "/terms", "/en/terms"]`), `features/landing/components/LandingPage.tsx` (footer), `routes/auth/register.tsx` (dòng "Khi tạo tài khoản bạn đồng ý Điều khoản và Chính sách quyền riêng tư"), `features/settings/components/SettingsPage.tsx` (link cuối trang)

Nội dung bắt buộc của Chính sách quyền riêng tư: dữ liệu lưu ở Neon (Singapore) và Qdrant Cloud, model chạy tại DeepInfra; quản trị viên có thể đọc hội thoại và dữ liệu để vận hành và việc đọc không được ghi nhật ký; nội dung nạp thuộc người dùng hoặc tổ chức; email dùng để gửi mã và lời mời. Điều khoản: câu trả lời không thay thế tư vấn của dược sĩ hoặc bác sĩ; cấm nạp nội dung vi phạm; tài khoản có thể bị khoá.

- [ ] **Step 1–5:** RED (trang render đủ các mục bắt buộc, có `<title>`), implement, GREEN, commit `feat(frontend): privacy policy and terms pages`.

### Task F11: E2E

**Files:**
- Modify: `backend/tests/e2e/server.py` (`POST /api/v1/__e2e/superadmin` body `{email}` set `is_superuser`; `e2e_container_factory` dùng `InProcessDispatcher` và `FakeEmbedder`; `GET /api/v1/__e2e/jobs/drain` chờ dispatcher rỗng)
- Create: `frontend/tests/e2e/organizations.e2e.ts`, `collections.e2e.ts`, `admin.e2e.ts`; modify `tests/e2e/support/api.ts` (`makeSuperadmin`, `latestInvitationLink`)

Bốn luồng theo spec mục 10:

```ts
test("owner invites by email, invitee registers, accepts and sees the collection as a source", async ({ page, request, browser }) => { ... })
test("a member invite waits for owner approval before the email goes out", ...)
test("an editor writes a document, publishes, and the answer cites it", ...)   // dùng ScenarioLlm của e2e server
test("a superadmin disables a user, whose session ends", ...)
```

- [ ] **Step 1:** viết spec; **Step 2:** `npm run e2e` → PASS 15/15 (11 cũ + 4 mới).
- [ ] **Step 3: Commit** — `git commit -m "test(e2e): organizations, publishing and admin flows"`.

---

### Task F12: Chuẩn hoá giao diện theo shadcn (sau quy tắc của người dùng ngày 2026-10-10)

Soát toàn bộ frontend và thay mọi chỗ tự ghép bằng hàng của shadcn (spec §8.1). Mỗi nhóm một commit refactor; test, lint, typecheck sạch sau mỗi nhóm.

- [x] Element của chat: `surfaces.tsx` xoá; `guardrail-notice`, `error-state` → `alert`; `inline-citation` → `hover-card`; `sources`, `retrieval-chunks` → `collapsible` + `item`; `feedback-dialog` → `toggle-group`, `textarea`, `button` (commit 28fd1b0).
- [x] Trình soạn bộ tài liệu: ô nhập cách dấu phẩy → `combobox` chip (`TagsInput`), chọn mục → `combobox` (`SectionPicker`), thanh công cụ → `toggle` + `button-group` + `tooltip`, class CSS tự viết → `prose` (commit f7803ac).
- [x] Nút Nguồn trong chat → `combobox` nhiều lựa chọn có nhóm (commit eb6c5be).
- [x] Danh sách `ul/li` → `item`, trạng thái rỗng → `empty`, 27 chỗ `<p role="alert">` → `alert`/`FieldError` (commit 9b03062).
- [x] Form `useState` còn lại → react-hook-form + zod + `field` (`NameForm`, form mời, trình soạn tài liệu) (commit e300330).
- [x] Trang quản trị dựng lại từ block `dashboard-01` (`site-header`, `section-cards`, `data-table` của block cho bốn bảng); xoá bản `DataTable` tự viết.
- [x] Khung ứng dụng: `AppSidebar` và `UserMenu` ghép từ `app-sidebar`, `nav-main`, `nav-secondary`, `nav-user` (có `avatar`) của block; đầu trang trong `routes/app/layout.tsx` là `site-header`. Giữ `ConversationSidebar` trong `SidebarContent`; test `AppSidebar.browser.test.tsx` cập nhật nhãn.
- [x] Dọn phần block không dùng (`nav-documents`, `chart-area-interactive`, demo route và `data.json`, `sonner`, `next-themes`, `@dnd-kit`, `recharts`), ghim phiên bản gói, `frontend/README.md` ghi quy tắc và các file `ui` khác registry.
- [x] Commit — `git commit -m "refactor(frontend): admin dashboard and app shell from the shadcn dashboard-01 block"`.

---

## Lớp G: triển khai và ra mắt

### Task G1: Compose profile, README, `.env.example`

**Files:**
- Modify: `compose.yaml` (services `llama-embedding`, `llama-reranker` → `profiles: ["local-models"]`; `cli-proxy-api` → `profiles: ["gemini-proxy"]`; `backend` bỏ `depends_on` hai llama khi không có profile: dùng `depends_on` với `required: false`), `README.md` (mục "Chạy local": mặc định `docker compose up -d postgres qdrant`, backend chạy `uv run pharma-agent serve` trên host với DeepInfra; "Chạy model trên CPU" với `--profile local-models`), `backend/.env.example` (mặc định trỏ DeepInfra, khối llama.cpp thành ghi chú), `backend/README.md`

- [ ] **Step 1:** Sửa; `docker compose config` phải parse; `docker compose --profile local-models config` liệt kê đủ service.
- [ ] **Step 2:** Chạy `uv run pytest tests/infrastructure/test_settings.py -q` (giá trị mặc định mới của `RerankSettings`/`EmbeddingSettings` nếu đổi) → PASS.
- [ ] **Step 3: Commit** — `git commit -m "chore(compose): local models and the Gemini proxy become optional profiles"`.

### Task G2: Vercel cho frontend

**Files:**
- `cd frontend && npm install @vercel/react-router` (ghim phiên bản)
- Modify: `frontend/react-router.config.ts` (`presets: [vercelPreset()]`), create `frontend/app/routes/api-proxy.ts`, modify `app/routes.ts`, `frontend/README.md` (mục Deploy), `frontend/.env.example` (`API_INTERNAL_URL`, `PUBLIC_SITE_URL`, `THEME_COOKIE_SECRET`)

Vercel không nội suy biến môi trường trong `vercel.json`, và rewrite của Vercel không cho kiểm soát header. Vì vậy proxy `/api/*` là một route của React Router: `app/routes/api-proxy.ts` đăng ký `route("api/*", "routes/api-proxy.ts")`, có `loader` và `action` chuyển tiếp request tới `process.env.API_INTERNAL_URL` bằng `fetch`, giữ method, headers (bỏ `host`), body, và trả `Response` gốc kèm `set-cookie`. Stream SSE đi qua vì `fetch` trả body dạng stream và React Router trả thẳng `Response`. Ở local, Vite proxy xử lý `/api` trước nên route này chỉ chạy trên bản build. Không tạo `vercel.json`.

- [ ] **Step 1: Test RED** (`app/routes/api-proxy.test.ts`, unit): loader chuyển `GET /api/v1/health` tới `API_INTERNAL_URL`, giữ `cookie`, bỏ `host`; action chuyển `POST` với body và `x-csrftoken`; response `set-cookie` được giữ.
- [ ] **Step 2–3:** implement, GREEN; `npm run build` thành công với preset.
- [ ] **Step 4:** Thêm `tests/e2e/proxy.ts` ghi chú vẫn dùng cho e2e (không đổi).
- [ ] **Step 5: Commit** — `git commit -m "feat(frontend): Vercel preset and a same-origin API proxy route"`.

### Task G3: Workflow deploy backend lên Cloud Run

**Files:**
- Create: `.github/workflows/deploy-backend.yml`, `devops/cloud-run/README.md` (bước tạo tài nguyên bằng `gcloud`, danh sách secret), `devops/cloud-run/service.yaml` (khai báo Cloud Run service: image, `--max-instances=1`, `--concurrency=40`, `--timeout=600`, `--cpu=1`, `--memory=1Gi`, env từ Secret Manager), `devops/cloud-run/migrate-job.yaml`
- Modify: `backend/src/pharma_agent/infrastructure/settings.py` (`ApiSettings.port` nhận thêm biến `PORT` do Cloud Run đặt: `validation_alias=AliasChoices("PHARMA_API__PORT", "PORT")`), `backend/tests/infrastructure/test_settings.py`. `Dockerfile` giữ nguyên.

Workflow (push `main`, đường dẫn `backend/**`, `pyproject.toml`, `uv.lock`): checkout → `google-github-actions/auth@v2` (WIF: `workload_identity_provider`, `service_account` từ secrets) → `gcloud auth configure-docker asia-southeast1-docker.pkg.dev` → `docker build -f backend/Dockerfile -t $IMAGE:$GITHUB_SHA .` → push → `gcloud run jobs update vipharmind-migrate --image $IMAGE:$GITHUB_SHA` và `gcloud run jobs execute vipharmind-migrate --wait` → `gcloud run deploy vipharmind-api --image $IMAGE:$GITHUB_SHA --region asia-southeast1` → smoke `curl -f $URL/api/v1/health`.

Secret Manager keys (tài liệu trong `devops/cloud-run/README.md`): `PHARMA_POSTGRES__DSN`, `PHARMA_QDRANT__URL`, `PHARMA_QDRANT__API_KEY`, `PHARMA_LLM__DEFAULT__API_KEY`, `PHARMA_RETRIEVAL__EMBEDDING__API_KEY`, `PHARMA_RETRIEVAL__RERANK__API_KEY`, `PHARMA_AUTH__JWT_SECRET`, `PHARMA_AUTH__CSRF_SECRET`, `PHARMA_AUTH__OTP_SECRET`, `PHARMA_AUTH__GOOGLE_CLIENT_SECRET`, `PHARMA_EMAIL__SMTP_PASSWORD`. Biến thường: `PHARMA_LLM__DEFAULT__BASE_URL=https://api.deepinfra.com/v1/openai`, `PHARMA_LLM__DEFAULT__MODEL=Qwen/Qwen3.5-9B`, `PHARMA_LLM__DEFAULT__EXTRA_BODY={"chat_template_kwargs":{"enable_thinking":false}}`, embedding và rerank DeepInfra, `PHARMA_RETRIEVAL__RERANK__PROTOCOL=deepinfra`, `PHARMA_SMS__PROVIDER=none`, `PHARMA_EMAIL__PROVIDER=smtp`, `PHARMA_AUTH__FRONTEND_URL=https://<project>.vercel.app`, `PHARMA_API__TRUSTED_PROXY_HOPS=1` (đo lại), `PHARMA_JOBS__DISPATCHER=cloud_tasks`, `PHARMA_JOBS__BACKEND_URL`, `PHARMA_JOBS__CLOUD_TASKS_PROJECT`, `PHARMA_JOBS__SERVICE_ACCOUNT_EMAIL`.

- [ ] **Step 1: Test RED** (`test_settings.py`): `PORT=8080` trong env → `settings.api.port == 8080`.
- [ ] **Step 2:** implement; `act` không cần; kiểm tra YAML bằng `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/deploy-backend.yml'))"`.
- [ ] **Step 3: Commit** — `git commit -m "ci: deploy the backend to Cloud Run with a migration job"`.

### Task G4: Nạp dữ liệu lần đầu và checklist ra mắt

**Files:**
- Create: `docs/launch-checklist.md` (checklist 9.5 của spec, lệnh `gcloud` tương ứng, `uv run pharma-agent corpus import pharma-lab/data/corpus/formulary --collection formulary --publish` với `PHARMA_*` trỏ production qua `--env-file backend/.env.production` — thêm tuỳ chọn `--env-file` cho CLI `corpus import`, `migrate`, `superadmin`), `backend/.env.production.example`
- Modify: `backend/src/pharma_agent/cli.py` (tuỳ chọn chung `--env-file`: `Settings(_env_file=path)`), `backend/tests/test_cli.py`
- Modify: `README.md` (mục Production: kiến trúc, đường scale, link checklist)

Checklist gồm cả bước đo `TRUSTED_PROXY_HOPS`: gọi `GET /api/v1/account/sessions` sau đăng nhập qua Vercel và xem `ip_address` có phải IP thật; nếu là IP của Vercel thì tăng lên 2.

- [ ] **Step 1: Test RED** (`test_cli.py`): `pharma-agent --env-file x.env check` đọc settings từ file đó.
- [ ] **Step 2–3:** implement, GREEN.
- [ ] **Step 4: Commit** — `git commit -m "docs: launch checklist and production env file support"`.

### Task G5: Review cuối toàn nhánh

Theo `superpowers:executing-plans`: `review-package` từ `git merge-base main HEAD` tới `HEAD`, reviewer trên model mạnh nhất, kèm mục Review Focus của plan này và các `Ruling:` trong ledger. Critical và Important sửa trong một lượt với test RED→GREEN; Minor ghi ledger.

---

## Tự kiểm tra plan

1. **Phủ spec:** mục 2 (quyết định) → B1, C2, D2, E4, E7, G3; mục 3 bảng quyền → B1; mục 4.1–4.4 → B3; 4.5 → B3; 4.6 → D1; 4.7 → E1; 4.8 → D1/D4; 4.9 → A1/A2; mục 5 → E2–E5, F6–F7; mục 6 → B4, C1–C5, D2–D3, E3–E7; mục 7 API → C4, D4, E5, E6; mục 8 frontend → F1–F10; mục 9 → G1–G4; mục 10 kiểm thử → test trong từng task, D5, F11, G3 smoke; mục 11 rủi ro 2 → F10; rủi ro 3 → E6 (`qdrant_points` trong `AdminCollectionView`).
2. **Placeholder:** không còn "TBD"; các task frontend liệt kê hành vi và test thay cho toàn bộ JSX, đây là mức chi tiết có chủ ý vì JSX lặp mẫu `ProfileForm`/`SessionsList` đã có trong repo và được dẫn trong Interfaces.
3. **Tên nhất quán:** đối chiếu sổ tên ở đầu plan; `ReleaseScope` (D3) dùng ở `TurnContext`, `ScopeResolver`, `RetrievalService`; `CollectionOwner` (D2) dùng ở E1, E3; `QuotaPolicy` (D2) dùng ở E3, E4 (`QuotaSettings` → `QuotaPolicy` trong `container.py`).
4. **Review Focus:** 1 → D5; 2 → E4; 3 → E2; 4 → C2; 5 → E4.
