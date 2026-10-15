# Paper v2, pha D (dữ liệu): tách leaflet theo heading, benchmark không rò rỉ, golden cập nhật

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng lại corpus với mỗi tờ hướng dẫn tách thành section theo heading, sinh lại benchmark retrieval 10.000 câu không còn gợi ý trong câu hỏi với nhãn nhóm đúng, cập nhật bộ golden e2e sang section mới, rồi chạy lại bảng retrieval trên release mới.

**Architecture:** Việc tách leaflet nằm ở bước `pharma-lab build` (`integrate_leaflets.py`), nên mọi thứ phía sau (bundle export, chunker backend, evaluation build, golden check) nhận section con mà không đổi contract. Builder benchmark bỏ ba chỗ nối hậu tố và hàm `unique_query`, đổi template thiếu chủ ngữ thành template có tên thuốc, đổi tên nhóm. Golden được remap bằng một lệnh CLI mới dựa trên quote của key fact. Embedding, import, retrieve, rerank và metrics dùng lệnh đã có trong guides, chạy trên Kaggle như v1, với tên run hậu tố `-v2`.

**Tech Stack:** Python 3.13, uv workspace (`pharma-lab` và `backend`), pytest, typer CLI `uv run pharma-lab`, Postgres và Qdrant của stack `vipharmind-eval`, Kaggle T4 qua `pharma-lab ... --backend kaggle`.

**Spec:** `docs/superpowers/specs/2026-10-14-paper-v2-design.md` mục 3.0; review dữ liệu `docs/research/paper-v2/07-dataset-review.md`; bản đồ mã `docs/research/paper-v2/06-repo-map.md`.

## Global Constraints

- Mọi lệnh `uv run pharma-lab` chạy trong `pharma-lab/`, `uv run pharma-agent` trong `backend/`, `docker compose` ở gốc repo (pharma-lab README).
- Gate trước mỗi commit: `uv run ruff check src tests && uv run ruff format --check src tests`, `uv run pyrefly check --min-severity warn`, `uv run pytest -q` trong `pharma-lab/` (và trong `backend/` khi đụng backend). Lỗi lint và type phải sửa trong mã, không thêm rule bỏ qua.
- Không thêm trailer "Co-Authored-By: Claude" vào commit.
- `MAX_CHUNK_CHARS = 3000` và `CHUNKER_VERSION = "chunker-v1"` trong `backend/src/pharma_agent/domain/corpus/chunking.py` giữ nguyên; release mới sinh ra từ digest bundle đổi, không từ chunker.
- Git chỉ giữ file nhỏ: `manifest.json`, `validation_report.json`, `run.json`, `report.md`, `metrics.jsonl`; dữ liệu lớn đi qua `pharma-lab data push` (`pharma-lab/data/README.md`).
- Key của section leaflet: trang là `leaflet:<category>:<slug>` (document), section con là `leaflet:<category>:<slug>:<NN>-<heading-slug>`; nhãn chunk gold vẫn là `<section_key>:chunk-<NNN>` một-based (`pharma_lab.bundle.chunks.gold_chunk_label`).
- Không viết tay câu hỏi mới cho benchmark; mọi câu sinh bằng luật từ template có tên thuốc.
- Số câu benchmark giữ 10.000, sáu nhóm: formulary 5000, leaflet 2500, chunk_risk 1000, leaflet_short 500, noisy 500, multi_intent 500.

## Review Focus

1. Tờ hướng dẫn không có heading nào (1 tờ trong corpus): phải vẫn thành đúng một section "Thông tin chi tiết" như cũ, không bị bỏ rơi. Test ở Task 1.
2. Heading lặp trong một tờ (ví dụ hai mục "Lưu ý"): key section phải khác nhau nhờ số thứ tự `NN`, không được ghi đè. Test ở Task 1.
3. Câu hỏi của hai section khác nhau trùng văn bản sau khi bỏ hậu tố (ví dụ hai hàm lượng của cùng thuốc): builder phải bỏ qua ứng viên trùng thay vì nối nhãn, và tổng vẫn đủ 10.000. Test ở Task 3.
4. Key fact có quote xuất hiện ở hai section con (câu lặp trong leaflet): remap phải chọn section có quote và ưu tiên section mà intent của câu hỏi gợi ý, và báo item nào mơ hồ thay vì chọn im lặng. Test ở Task 5.
5. `typo_query` không được chạm vào chữ số và đơn vị liều (ví dụ "500 mg"), vì đổi số là đổi câu hỏi. Test ở Task 3.

---

### Task 1: Tách tờ hướng dẫn theo heading khi build corpus

**Files:**
- Modify: `pharma-lab/src/pharma_lab/corpus/crawling/integrate_leaflets.py:55-56` (`build_context_header`), `:1030-1135` (`integrate_drug_file`), `:1228-1266` (`integrate_leaflet_corpus`)
- Test: `pharma-lab/tests/corpus/test_integrate_leaflets.py` (mới)

**Interfaces:**
- Consumes: `chunk_text(text, max_chars)`, `product_names_from_title(title)`, `resolve_colloquial_mapping(slug, mappings)`, `compact_colloquial_mapping(...)`, `has_meaningful_section_body(content)` đã có trong file.
- Produces: `split_leaflet_sections(content: str) -> list[LeafletPart]` với `LeafletPart(heading: str, markdown: str)`; `heading_slug(heading: str) -> str`; `integrate_drug_file(file_path, *, markdown_root, mappings) -> tuple[list[dict], list[dict]]` trả về danh sách section record (mỗi record có thêm trường `"page_id"`) và chunk record. Task 2 đọc `page_id`.

- [ ] **Step 1: Viết test thất bại cho hàm tách**

```python
# pharma-lab/tests/corpus/test_integrate_leaflets.py
from pathlib import Path

from pharma_lab.corpus.crawling.integrate_leaflets import (
    heading_slug,
    integrate_drug_file,
    split_leaflet_sections,
)

PAGE = (
    "# Abanuti 1 g trị thiếu Carnitine (20 ống x 10 ml)\n\n"
    "### 1. Thành phần\n\nLevocarnitin 1,0 g.\n\n"
    "### 2. Công dụng (Chỉ định)\n\nThiếu hụt carnitine.\n\n"
    "### 3. Cách dùng - Liều dùng\n\nNgười lớn 1 đến 3 g/ngày.\n\n"
    "#### - Quá liều\n\nCó thể gây tiêu chảy.\n\n"
    "### 4. Lưu ý\n\nTheo dõi carnitin huyết tương.\n\n"
    "### 5. Lưu ý\n\nKhông dùng đường tiêm.\n"
)


def test_split_keeps_level_four_subheadings_inside_their_parent() -> None:
    parts = split_leaflet_sections(PAGE)
    assert [part.heading for part in parts] == [
        "Thành phần",
        "Công dụng (Chỉ định)",
        "Cách dùng - Liều dùng",
        "Lưu ý",
        "Lưu ý",
    ]
    assert "#### - Quá liều" in parts[2].markdown
    assert parts[2].markdown.startswith("### 3. Cách dùng - Liều dùng")


def test_split_without_headings_returns_one_general_part() -> None:
    parts = split_leaflet_sections("# Thuốc X\n\nChỉ một đoạn mô tả.")
    assert len(parts) == 1
    assert parts[0].heading == "Thông tin chi tiết"
    assert parts[0].markdown == "Chỉ một đoạn mô tả."


def test_split_keeps_text_before_first_heading_as_general_part() -> None:
    parts = split_leaflet_sections(
        "# Thuốc X\n\nMô tả chung.\n\n### 1. Thành phần\n\nA 1 mg."
    )
    assert [part.heading for part in parts] == ["Thông tin chi tiết", "Thành phần"]


def test_heading_slug_strips_numbering_and_dashes() -> None:
    assert heading_slug("3. Cách dùng - Liều dùng") == "cach-dung-lieu-dung"
    assert heading_slug("- Bảo quản") == "bao-quan"


def test_integrate_drug_file_emits_one_section_per_heading(tmp_path: Path) -> None:
    root = tmp_path / "md"
    (root / "thuoc-bo").mkdir(parents=True)
    (root / "thuoc-bo" / "abanuti-1g.md").write_text(PAGE, encoding="utf-8")
    sections, chunks = integrate_drug_file(
        root / "thuoc-bo" / "abanuti-1g.md", markdown_root=root, mappings={}
    )
    assert [section["id"] for section in sections] == [
        "leaflet:thuoc-bo:abanuti-1g:01-thanh-phan",
        "leaflet:thuoc-bo:abanuti-1g:02-cong-dung-chi-dinh",
        "leaflet:thuoc-bo:abanuti-1g:03-cach-dung-lieu-dung",
        "leaflet:thuoc-bo:abanuti-1g:04-luu-y",
        "leaflet:thuoc-bo:abanuti-1g:05-luu-y",
    ]
    first = sections[0]
    assert first["page_id"] == "leaflet:thuoc-bo:abanuti-1g"
    assert first["section"] == "Thành phần"
    assert first["context_path"] == ["Thành phần"]
    assert first["context_header"] == (
        "Abanuti 1 g trị thiếu Carnitine (20 ống x 10 ml)\n> Thành phần"
    )
    assert first["text"].startswith(
        "# Abanuti 1 g trị thiếu Carnitine (20 ống x 10 ml)\n\n### 1. Thành phần"
    )
    assert first["colloquial_mapping"] == sections[1]["colloquial_mapping"]
    assert chunks[0]["id"] == "leaflet:thuoc-bo:abanuti-1g:01-thanh-phan:chunk-001"
    assert chunks[0]["section_id"] == first["id"]
    assert chunks[0]["page_id"] == first["page_id"]
```

- [ ] **Step 2: Chạy test để thấy thất bại**

Run: `cd pharma-lab && uv run pytest tests/corpus/test_integrate_leaflets.py -q`
Expected: FAIL với `ImportError: cannot import name 'split_leaflet_sections'`.

- [ ] **Step 3: Cài hàm tách và sửa `integrate_drug_file`**

Thêm vào `integrate_leaflets.py` sau `build_context_header` (giữ hàm cũ cho tương thích, thêm tham số heading):

```python
from dataclasses import dataclass

from pharma_lab.corpus.processing.preprocess_rag_corpus import slugify

GENERAL_LEAFLET_HEADING = "Thông tin chi tiết"
# Mục của tờ hướng dẫn là heading cấp 2 hoặc 3; cấp 4 ("#### - Quá liều") là mục con, ở lại trong mục cha.
_PART_HEADING = re.compile(r"(?m)^(#{2,3})[ \t]+(.+?)[ \t]*$")


@dataclass(frozen=True)
class LeafletPart:
    heading: str
    markdown: str


def clean_leaflet_heading(raw: str) -> str:
    text = normalize_inline_spaces(raw)
    text = re.sub(r"^[-–—*•]+\s*", "", text)
    text = re.sub(r"^\d+\s*[.)]\s*", "", text)
    return text.strip() or GENERAL_LEAFLET_HEADING


def heading_slug(heading: str) -> str:
    return slugify(clean_leaflet_heading(heading), max_length=60)


def build_context_header(title: str, heading: str = GENERAL_LEAFLET_HEADING) -> str:
    return f"{(title or '').strip()}\n> {heading}".strip()


def split_leaflet_sections(content: str) -> list[LeafletPart]:
    """Mỗi heading cấp 2/3 mở một mục; văn bản trước heading đầu thành mục chung nếu có nghĩa."""
    body = re.sub(r"^# .*(?:\n|$)", "", content, count=1)
    matches = list(_PART_HEADING.finditer(body))
    if not matches:
        text = body.strip()
        return [LeafletPart(GENERAL_LEAFLET_HEADING, text)] if text else []
    parts: list[LeafletPart] = []
    preamble = body[: matches[0].start()].strip()
    if preamble and has_meaningful_section_body(preamble):
        parts.append(LeafletPart(GENERAL_LEAFLET_HEADING, preamble))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        markdown = body[match.start() : end].strip()
        parts.append(LeafletPart(clean_leaflet_heading(match.group(2)), markdown))
    return parts
```

Thay thân `integrate_drug_file` từ dòng `section_id = f"leaflet:{category}:{slug}"` đến `return section_record, chunk_records` bằng:

```python
page_id = f"leaflet:{category}:{slug}"
colloquial_mapping = compact_colloquial_mapping(
    {
        "colloquial_mapping_key": colloquial_mapping_key,
        "product_aliases": aliases,
        "visual_sign": visual_sign,
        "product_names": product_names_from_title(title) or [title],
    }
)
section_records: list[dict] = []
chunk_records: list[dict] = []
for index, part in enumerate(split_leaflet_sections(content), start=1):
    if not has_meaningful_section_body(part.markdown):
        continue
    section_id = f"{page_id}:{index:02d}-{heading_slug(part.heading)}"
    text = f"# {title}\n\n{part.markdown}"
    strategy = "chunk_window" if len(text) > FULL_SECTION_MAX_CHARS else "full_section"
    context_path = [part.heading]
    context_header = build_context_header(title, part.heading)
    common = {
        "page_id": page_id,
        "content_type": "brand_page",
        "title": title,
        "section": part.heading,
        "source": INSTRUCTION_LEAFLET_SOURCE,
        "context_path": context_path,
        "context_header": context_header,
        "colloquial_mapping": colloquial_mapping,
        "start_page": 0,
        "end_page": 0,
        "warnings": [],
        "hydrate_strategy": strategy,
        "section_char_count": len(text),
    }
    section_records.append({"id": section_id, "text": text, **common})
    for chunk_index, chunk_text_content in enumerate(chunk_text(text), 1):
        chunk_records.append(
            {
                "id": f"{section_id}:chunk-{chunk_index:03d}",
                "section_id": section_id,
                "text": chunk_text_content,
                "chunk_role": "prose",
                "chunk_content_type": "paragraph",
                "chunk_index": chunk_index,
                **common,
            }
        )
return section_records, chunk_records
```

Đổi chữ ký và đầu hàm: `def integrate_drug_file(file_path, *, markdown_root: Path, mappings=None) -> tuple[list[dict], list[dict]]:` và chỗ `return None, []` thành `return [], []`. Trong `integrate_leaflet_corpus`, thay

```python
        sec, chks = integrate_drug_file(...)
        if sec is None:
            continue
        new_sections.append(sec)
        new_chunks.extend(chks)
```

bằng

```python
        secs, chks = integrate_drug_file(
            file_path, markdown_root=markdown_dir, mappings=mappings
        )
        new_sections.extend(secs)
        new_chunks.extend(chks)
```

- [ ] **Step 4: Chạy test**

Run: `cd pharma-lab && uv run pytest tests/corpus/test_integrate_leaflets.py -q`
Expected: 5 passed.

- [ ] **Step 5: Chạy toàn bộ test, lint, type và commit**

Run: `cd pharma-lab && uv run ruff check src tests && uv run ruff format src tests && uv run pyrefly check --min-severity warn && uv run pytest -q`
Expected: tất cả xanh (test export và golden hiện có vẫn dùng fixture key 3 phần nên không đổi).

```bash
git add pharma-lab/src/pharma_lab/corpus/crawling/integrate_leaflets.py pharma-lab/tests/corpus/test_integrate_leaflets.py
git commit -m "feat(pharma-lab): split each leaflet into one section per markdown heading"
```

---

### Task 2: Bundle export gom section con về đúng document của tờ

**Files:**
- Modify: `pharma-lab/src/pharma_lab/bundle/export.py:82-93` (`document_for_section`), `:114-175` (`export_bundle`, gọi `add_leaflet`), `:240-244` (`_leaflet_path`)
- Modify: `pharma-lab/tests/fixtures/rag_final_small/sections.jsonl` (thêm hai dòng), `pharma-lab/tests/fixtures/rag_final_small/manifest.json` nếu có đếm section (xem Step 1)
- Test: `pharma-lab/tests/bundle/test_export.py`

**Interfaces:**
- Consumes: trường `page_id` trên section leaflet (Task 1); dòng cũ không có `page_id` vẫn được chấp nhận (document = key của section).
- Produces: `DocumentRecord.key` của leaflet = `page_id`; `SectionRecord.ordinal` tăng theo thứ tự section con; `_MappingCollector.add_leaflet` được gọi một lần mỗi document.

- [ ] **Step 1: Thêm fixture và test thất bại**

Kiểm tra fixture có đếm section không: `grep -n "section" pharma-lab/tests/fixtures/rag_final_small/manifest.json`. Nếu manifest chứa `section_count`, cộng thêm 2. Thêm vào cuối `tests/fixtures/rag_final_small/sections.jsonl` hai dòng (một tờ, hai section con; `blocks.jsonl` không cần dòng vì leaflet lấy block từ `text`):

```json
{"id": "leaflet:thuoc:efferalgan-500-11600:01-thanh-phan", "page_id": "leaflet:thuoc:efferalgan-500-11600", "content_type": "brand_page", "title": "Efferalgan 500 mg (hộp 16 viên)", "section": "Thành phần", "text": "# Efferalgan 500 mg (hộp 16 viên)\n\n### 1. Thành phần\n\nParacetamol 500 mg.", "source": "Tờ hướng dẫn sử dụng", "context_path": ["Thành phần"], "context_header": "Efferalgan 500 mg (hộp 16 viên)\n> Thành phần", "colloquial_mapping": {"product_names": ["Efferalgan 500 mg"]}, "start_page": 0, "end_page": 0, "warnings": [], "hydrate_strategy": "full_section", "section_char_count": 60}
{"id": "leaflet:thuoc:efferalgan-500-11600:02-cach-dung-lieu-dung", "page_id": "leaflet:thuoc:efferalgan-500-11600", "content_type": "brand_page", "title": "Efferalgan 500 mg (hộp 16 viên)", "section": "Cách dùng - Liều dùng", "text": "# Efferalgan 500 mg (hộp 16 viên)\n\n### 2. Cách dùng - Liều dùng\n\nNgười lớn 1 viên mỗi 4-6 giờ.", "source": "Tờ hướng dẫn sử dụng", "context_path": ["Cách dùng - Liều dùng"], "context_header": "Efferalgan 500 mg (hộp 16 viên)\n> Cách dùng - Liều dùng", "colloquial_mapping": {"product_names": ["Efferalgan 500 mg"]}, "start_page": 0, "end_page": 0, "warnings": [], "hydrate_strategy": "full_section", "section_char_count": 80}
```

Thêm test vào `tests/bundle/test_export.py`:

```python
EFFERALGAN = "leaflet:thuoc:efferalgan-500-11600"


def test_export_groups_leaflet_subsections_under_one_document(tmp_path: Path) -> None:
    export_bundle(_request(tmp_path / "bundle"))
    bundle = read_bundle(tmp_path / "bundle")
    documents = {document.key: document for document in bundle.documents}
    assert documents[EFFERALGAN].kind is DocumentKind.LEAFLET
    assert documents[EFFERALGAN].title == "Efferalgan 500 mg (hộp 16 viên)"
    subsections = [s for s in bundle.sections if s.document_key == EFFERALGAN]
    assert [s.key for s in subsections] == [
        f"{EFFERALGAN}:01-thanh-phan",
        f"{EFFERALGAN}:02-cach-dung-lieu-dung",
    ]
    assert [s.ordinal for s in subsections] == [1, 2]
    assert subsections[1].heading == "Cách dùng - Liều dùng"
    assert subsections[1].context_path == ["Cách dùng - Liều dùng"]
    mapping = next(
        m for m in bundle.colloquial_mappings if EFFERALGAN in m.section_keys
    )
    assert mapping.section_keys.count(EFFERALGAN) == 1
```

- [ ] **Step 2: Chạy test để thấy thất bại**

Run: `cd pharma-lab && uv run pytest tests/bundle/test_export.py -q`
Expected: FAIL (`ValueError: Document key ... is shared` hoặc hai document riêng).

- [ ] **Step 3: Sửa export**

```python
def _leaflet_path(section_key: str) -> tuple[str, str]:
    parts = section_key.removeprefix(LEAFLET_SECTION_PREFIX).split(":")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Leaflet section key is malformed: {section_key}")
    return parts[0], parts[1]


def leaflet_document_key(row: Mapping[str, Any]) -> str:
    """Key của tờ: ``page_id`` nếu có, nếu không là key section (bundle cũ, một section mỗi tờ)."""
    page_id = str(row.get("page_id") or "")
    if page_id:
        return page_id
    category, slug = _leaflet_path(str(row["id"]))
    return f"{LEAFLET_SECTION_PREFIX}{category}:{slug}"
```

Trong `document_for_section`, nhánh leaflet dùng `key=leaflet_document_key(row)`. Trong `export_bundle`, thay `mappings.add_leaflet(section_key, document.title)` bằng:

```python
        if is_leaflet and document.key not in mapped_documents:
            mapped_documents.add(document.key)
            mappings.add_leaflet(document.key, document.title)
```

với `mapped_documents: set[str] = set()` khai báo cạnh `documents`. `_MappingCollector.add_leaflet` gọi `_leaflet_path(section_key)` để lấy slug: giờ nhận key document 3 phần nên vẫn đúng.

- [ ] **Step 4: Chạy test**

Run: `cd pharma-lab && uv run pytest tests/bundle tests/e2e/test_golden.py -q`
Expected: pass (các test khác của fixture vẫn qua vì chỉ thêm dòng).

- [ ] **Step 5: Lint, type, commit**

```bash
cd pharma-lab && uv run ruff check src tests && uv run ruff format src tests && uv run pyrefly check --min-severity warn && uv run pytest -q
git add pharma-lab/src/pharma_lab/bundle/export.py pharma-lab/tests/bundle/test_export.py pharma-lab/tests/fixtures/rag_final_small
git commit -m "feat(pharma-lab): export leaflet subsections under one document"
```

---

### Task 3: Builder benchmark không rò rỉ, nhóm đúng tên, không độ khó, intent tách

**Files:**
- Modify: `pharma-lab/src/pharma_lab/evaluation/section_eval_schema.py` (quota, nhóm, query form, intent, EVAL_HEADER, bỏ difficulty, FORMULARY_CATEGORY_MAP)
- Modify: `pharma-lab/src/pharma_lab/evaluation/build_section_retrieval_eval.py` (`unique_query`, `auto_query_for_chunk`, `make_leaflet_row`, `make_colloquial_alias_row`, `leaflet_query_for_category`, template brand_lookup, `noisy_query` + `typo_query`, vòng `for query_style`, `eval_group_for_row`, `make_row`, `validate_rows`, `load_patient_queries`, `generate_rows` thêm any_acceptable theo chunk trùng)
- Modify: `pharma-lab/src/pharma_lab/evaluation/patient_query_generation.py` (bỏ `difficulty`)
- Modify: `pharma-lab/src/pharma_lab/evaluation/metrics_service.py:48` (`BREAKDOWN_DIMENSIONS = ("eval_group",)`), `:49-52` (nhãn hiển thị)
- Modify: `pharma-lab/src/pharma_lab/e2e/golden.py:21-28` (`EVAL_GROUPS`), `pharma-lab/src/pharma_lab/e2e/sampling.py:38,176-181` (strata chỉ theo answer_mode)
- Test: `pharma-lab/tests/evaluation/test_build_section_retrieval_eval.py` (mới)

**Interfaces:**
- Produces: `typo_query(query: str, seed: int) -> str`; `display_product_name(section: dict) -> str`; `unique_query(query, seen_queries) -> str | None`; hằng `NOISY_QUERY_FORM_TARGETS = {"noisy": 300, "typo": 200}`; nhóm `leaflet_short`, `noisy`; intent thêm `overdose`.

- [ ] **Step 1: Viết test thất bại**

```python
# pharma-lab/tests/evaluation/test_build_section_retrieval_eval.py
import json
from pathlib import Path

from pharma_lab.evaluation import build_section_retrieval_eval as b
from pharma_lab.evaluation.section_eval_schema import (
    ALLOWED_EVAL_GROUPS,
    ALLOWED_INTENT_CATEGORIES,
    ALLOWED_QUERY_FORMS,
    EVAL_HEADER,
    FORMULARY_CATEGORY_MAP,
)


def _leaflet_section(key: str, title: str, heading: str, text: str) -> dict:
    return {
        "id": key,
        "page_id": key.rsplit(":", 1)[0],
        "content_type": "brand_page",
        "title": title,
        "section": heading,
        "text": f"# {title}\n\n### 3. {heading}\n\n{text}",
        "context_path": [heading],
        "colloquial_mapping": {"product_names": [title, "Fordia 850 mg"]},
        "hydrate_strategy": "full_section",
        "section_char_count": 120,
    }


def test_schema_has_no_difficulty_and_new_groups() -> None:
    assert "difficulty" not in EVAL_HEADER
    assert ALLOWED_EVAL_GROUPS == {
        "formulary",
        "leaflet",
        "chunk_risk",
        "leaflet_short",
        "noisy",
        "multi_intent",
    }
    assert "confuser" not in ALLOWED_QUERY_FORMS and "typo" in ALLOWED_QUERY_FORMS
    assert "overdose" in ALLOWED_INTENT_CATEGORIES
    assert FORMULARY_CATEGORY_MAP["overdose"] == ("overdose", "formulary_overdose")
    assert FORMULARY_CATEGORY_MAP["storage"] == ("storage", "formulary_storage")


def test_unique_query_returns_none_instead_of_appending_a_label() -> None:
    seen = {"liều abacavir?"}
    assert b.unique_query("Liều abacavir?", seen) is None
    assert b.unique_query("Liều acarbose?", seen) == "Liều acarbose?"


def test_leaflet_queries_use_short_product_name_and_no_hint() -> None:
    section = _leaflet_section(
        "leaflet:tieu-duong:fordia-850:03-cach-dung-lieu-dung",
        "Fordia 850 mg trị đái tháo đường type 2 kết hợp ăn kiêng (10 vỉ x 10 viên)",
        "Cách dùng - Liều dùng",
        "Người lớn 1 viên x 2 lần/ngày.",
    )
    assert b.display_product_name(section) == "Fordia 850 mg"
    query, _style = b.leaflet_query_for_category(section, "brand_dosage")
    assert query == "Fordia 850 mg dùng liều thế nào?"
    chunk = {
        "chunk_id": f"{section['id']}:chunk-001",
        "chunk_text": section["text"],
        "section_id": section["id"],
        "chunk_index": 1,
    }
    assert "(phần" not in b.auto_query_for_chunk(chunk, section, "brand_dosage")
    row = b.make_leaflet_row("q1", section, chunk, "brand_dosage")
    assert "(" not in row["query"]
    assert "difficulty" not in row


def test_typo_query_is_deterministic_and_keeps_numbers() -> None:
    query = "Paracetamol 500 mg uống tối đa bao nhiêu viên mỗi ngày?"
    first = b.typo_query(query, seed=7)
    assert first == b.typo_query(query, seed=7)
    assert first != query
    assert "500 mg" in first


def test_brand_lookup_templates_name_the_brand() -> None:
    for templates in (
        b.PARAPHRASE_TEMPLATES,
        b.NATURAL_TEMPLATES,
        b.CLINICAL_TEMPLATES,
    ):
        for template in templates["brand_lookup"]:
            assert "{brand}" in template


def test_duplicate_chunk_text_widens_expected_sections() -> None:
    a = _leaflet_section(
        "leaflet:t:jardiance-10:01-thanh-phan",
        "Jardiance 10 mg",
        "Thành phần",
        "Empagliflozin.",
    )
    c = _leaflet_section(
        "leaflet:t:jardiance-25:01-thanh-phan",
        "Jardiance 25 mg",
        "Thành phần",
        "Empagliflozin.",
    )
    chunks = [
        {
            "chunk_id": f"{a['id']}:chunk-001",
            "section_id": a["id"],
            "chunk_text": "Empagliflozin.",
            "chunk_index": 1,
        },
        {
            "chunk_id": f"{c['id']}:chunk-001",
            "section_id": c["id"],
            "chunk_text": "Empagliflozin.",
            "chunk_index": 1,
        },
    ]
    row = b.make_leaflet_row("q1", a, chunks[0], "brand_ingredient")
    widened = b.widen_duplicate_text_rows([row], chunks)
    assert widened[0]["expected_section_ids"] == [a["id"], c["id"]]
    assert widened[0]["answer_mode"] == "any_acceptable"
    assert "duplicate_text" in widened[0]["eval_tags"]
```

- [ ] **Step 2: Chạy test để thấy thất bại**

Run: `cd pharma-lab && uv run pytest tests/evaluation/test_build_section_retrieval_eval.py -q`
Expected: FAIL ở nhiều test (`difficulty` còn trong header, `unique_query` sai chữ ký, thiếu `typo_query`, `display_product_name`, `widen_duplicate_text_rows`).

- [ ] **Step 3: Sửa `section_eval_schema.py`**

```python
DEFAULT_EVAL_GROUP_QUOTAS = {
    "formulary": 5000,
    "leaflet": 2500,
    "leaflet_short": 500,
    "chunk_risk": 1000,
    "multi_intent": 500,
    "noisy": 500,
}

NOISY_QUERY_FORM_TARGETS = {"noisy": 300, "typo": 200}
```

Xóa `NOISY_CONFUSER_QUERY_FORM_TARGETS`, xóa `"difficulty"` khỏi `EVAL_HEADER`, xóa `ALLOWED_DIFFICULTIES`. Trong `ALLOWED_QUERY_FORMS` bỏ `"confuser"`, bỏ `"patient"`, thêm `"typo"` và `"leaflet_short"`. Thêm `"overdose"` vào `ALLOWED_INTENT_CATEGORIES`. Thêm vào `FORMULARY_CATEGORY_MAP`:

```python
    "overdose": ("overdose", "formulary_overdose"),
    "storage": ("storage", "formulary_storage"),
    "pharmacology": ("pharmacology", "formulary_pharmacology"),
    "precaution": ("precaution", "formulary_precaution"),
    "dosage_form": ("general_info", "formulary_dosage_form"),
```

- [ ] **Step 4: Sửa builder**

(a) `unique_query`:

```python
def unique_query(query: str, seen_queries: set[str]) -> str | None:
    """Câu hỏi đã dùng cho section khác thì bỏ ứng viên, không nối nhãn mục vào câu."""
    normalized = normalize_spaces(query)
    if normalized.lower() in seen_queries:
        return None
    return normalized
```

Mọi chỗ gọi `unique_query(query, section, seen)` đổi thành `unique_query(query, seen)` và `if query is None: continue` (hoặc `return False` trong `append_*_row`). Tìm bằng `grep -n "unique_query(" build_section_retrieval_eval.py`.

(b) Bỏ hậu tố: trong `auto_query_for_chunk` nhánh leaflet trả `query` thẳng (xóa `label` và `(phần ...)`); nhánh không leaflet xóa hai dòng `if label and ...: return f"{query} (phần {label})"`. Trong `make_leaflet_row` và `make_colloquial_alias_row` xóa khối `if chunk: label = ...; if label ...: query = f"{query} (phần {label})"`.

(c) Tên sản phẩm ngắn:

```python
def display_product_name(section: dict) -> str:
    names = [
        normalize_spaces(str(name))
        for name in (section.get("colloquial_mapping") or {}).get("product_names", [])
        if str(name).strip()
    ]
    if names:
        return min(names, key=len)
    return normalize_spaces(section.get("title", ""))


def leaflet_query_for_category(section: dict, category: str) -> tuple[str, str]:
    template, style = LEAFLET_QUERY_TEMPLATES.get(
        category, LEAFLET_QUERY_TEMPLATES["brand_product"]
    )
    return template.format(title=display_product_name(section)), style
```

Với section con, `leaflet_categories_for_text` vẫn đọc heading từ `text` nên `leaflet_candidates` giữ nguyên; chỉ cần mỗi section con cho đúng một category.

(d) brand_lookup có chủ ngữ: thay ba nhóm template `"brand_lookup"` (PARAPHRASE, NATURAL, CLINICAL) bằng template có `{brand}`:

```python
    "brand_lookup": [
        "{brand} là biệt dược của hoạt chất nào?",
        "{brand} chứa hoạt chất gì?",
        "Thuốc {brand} tương ứng với hoạt chất nào trong Dược thư?",
    ],
```

và trong `styled_query_for_section` thêm trước `query = options[...]`:

```python
brand = (brand_names or [title])[variant_index % max(1, len(brand_names or [title]))]
query = options[variant_index % len(options)].format(
    title=title, label=label, brand=brand
)
```

(`brand_names` đã là tham số và `generate_rows` truyền `brand_names_by_title.get(title)` từ `extract_brand_names(sections)` ở dòng 1525 và 1562; section không có tên biệt dược thì bỏ qua category brand_lookup: thêm `if category == "brand_lookup" and not brand_names: return ""` đầu hàm và để `append_section_row` bỏ qua query rỗng.)

(e) Lỗi gõ thật, thay confuser:

```python
_TYPO_PROTECTED = re.compile(r"\d|mg|ml|mcg|iu|%|g\b")


def typo_query(query: str, seed: int) -> str:
    """Một đến hai lỗi gõ (đổi chỗ, bỏ, lặp ký tự) trên từ dài, không chạm số và đơn vị."""
    rng = random.Random(seed)
    words = query.split()
    candidates = [
        index
        for index, word in enumerate(words)
        if len(word) >= 5 and not _TYPO_PROTECTED.search(word.lower())
    ]
    if not candidates:
        return query
    for index in rng.sample(candidates, k=min(2, len(candidates))):
        word = words[index]
        position = rng.randrange(1, len(word) - 1)
        kind = rng.choice(("swap", "drop", "double"))
        if kind == "swap":
            word = (
                word[: position - 1]
                + word[position]
                + word[position - 1]
                + word[position + 1 :]
            )
        elif kind == "drop":
            word = word[:position] + word[position + 1 :]
        else:
            word = word[: position + 1] + word[position] + word[position + 1 :]
        words[index] = word
    return " ".join(words)
```

Trong `styled_query_for_section`: xóa nhánh `elif query_style == "confuser"`, thêm `if query_style == "typo": return typo_query(query, seed=variant_index * 7919 + len(query))` ngay trước `if query_style == "noisy"`. Xóa `CONFUSER_TEMPLATES`. Trong vòng `for query_style in (...)` thay `"confuser"` bằng `"typo"`. `style_targets.update(weighted_targets(NOISY_QUERY_FORM_TARGETS, quotas["noisy"]))`. `eval_group_for_row`: `if query_form in {"noisy", "typo"}: return "noisy"`; `if query_form == "leaflet_short": return "leaflet_short"`. Mọi chuỗi `"noisy_confuser"` và `"patient_natural"` trong file đổi tương ứng (`grep -n "noisy_confuser\|patient_natural\|\"patient\"" build_section_retrieval_eval.py`), `query_form_for_style("patient_natural")` trả `"leaflet_short"`.

(f) Bỏ difficulty: xóa tham số `difficulty` khỏi `make_row` và mọi lời gọi (`grep -n "difficulty" build_section_retrieval_eval.py patient_query_generation.py`), xóa `("difficulty", ALLOWED_DIFFICULTIES)` trong `validate_rows`, `SECTION_CATEGORY_RULES` giữ cột thứ ba nhưng không ghi ra hàng. Trong `patient_query_generation.row_for_candidate` bỏ `"difficulty"`. Trong `load_patient_queries` không đọc `item["difficulty"]` (dùng `item.get`), `eval_group="leaflet_short"`, `query_form="leaflet_short"`, tags `["leaflet_short", category]`.

(g) any_acceptable cho chunk trùng văn bản:

```python
def widen_duplicate_text_rows(rows: list[dict], chunks: list[dict]) -> list[dict]:
    """Chunk gold có văn bản trùng ở section khác (cùng thuốc, khác hàm lượng) thì chấp nhận cả hai."""
    owners: dict[str, set[str]] = defaultdict(set)
    text_by_chunk: dict[str, str] = {}
    for chunk in chunks:
        key = normalize_spaces(chunk_body_text(chunk)).lower()
        owners[key].add(str(chunk.get("section_id")))
        text_by_chunk[chunk_identifier(chunk)] = key
    for row in rows:
        chunk_id = row.get("expected_chunk_id") or ""
        if not chunk_id or row.get("answer_mode") != "single":
            continue
        others = sorted(
            owners.get(text_by_chunk.get(chunk_id, ""), set())
            - {row["expected_section_id"]}
        )
        if not others:
            continue
        row["expected_section_ids"] = [row["expected_section_id"], *others]
        row["answer_mode"] = "any_acceptable"
        row["eval_tags"] = [*row.get("eval_tags", []), "duplicate_text"]
    return rows
```

Gọi `rows = widen_duplicate_text_rows(rows, chunks)` trong `generate_rows` ngay trước `validate_rows(...)`.

(h) `metrics_service.BREAKDOWN_DIMENSIONS = ("eval_group",)` và `EVAL_GROUP_DISPLAY_LABELS` thêm `"leaflet_short": "leaflet_short_template"`. `golden.EVAL_GROUPS` đổi hai tên. `sampling.py`: `key = str(row.get("answer_mode"))` và `_stratum` trả `(eval_group, answer_mode)`; cập nhật test `tests/e2e/test_sampling.py` nếu nó kiểm tra tuple 3 phần.

- [ ] **Step 5: Chạy test**

Run: `cd pharma-lab && uv run pytest tests/evaluation/test_build_section_retrieval_eval.py tests/e2e -q`
Expected: pass. Test e2e golden có thể cần đổi `eval_group` trong factory từ `"formulary"` (giữ) và trong `test_golden.py` nếu liệt kê nhóm cũ.

- [ ] **Step 6: Lint, type, commit**

```bash
cd pharma-lab && uv run ruff check src tests && uv run ruff format src tests && uv run pyrefly check --min-severity warn && uv run pytest -q
git add pharma-lab/src/pharma_lab/evaluation pharma-lab/src/pharma_lab/e2e/golden.py pharma-lab/src/pharma_lab/e2e/sampling.py pharma-lab/tests
git commit -m "feat(pharma-lab): leak-free benchmark queries, renamed groups, typo variants, no difficulty"
```

---

### Task 4: Dựng lại corpus, bundle và kiểm tra số liệu

**Files:**
- Chạy lệnh; sửa `pharma-lab/docs/guides/workflow-local-kaggle.md` nếu lệnh đổi (không đổi).

**Interfaces:**
- Produces: `pharma-lab/data/corpus/rag-final/` và `pharma-lab/data/corpus/formulary/` mới; `manifest.json` và `validation_report.json` được commit.

- [ ] **Step 1: Build và validate**

Run (trong `pharma-lab/`, trong tmux vì build vài phút):
```bash
uv run pharma-lab build
uv run pharma-lab validate
```
Expected: `validate` không có `errors`; `validation_report.json` không có finding mới loại `leaflet` (audit kiểm tra text bắt đầu bằng `# `, Task 1 đã giữ H1).

- [ ] **Step 2: Export bundle và đếm**

```bash
uv run pharma-lab bundle export --output data/corpus/formulary --force
uv run python - <<'EOF'
import json, collections
from pathlib import Path
from pharma_agent.domain.corpus.bundle import read_bundle
from pharma_lab.bundle.chunks import iter_section_chunks
b = read_bundle(Path("data/corpus/formulary"))
kinds = collections.Counter(d.kind.value for d in b.documents)
per_doc = collections.Counter(s.document_key for s in b.sections if s.key.startswith("leaflet:"))
chunks = sum(len(sc.drafts) for sc in iter_section_chunks(b))
print("documents", dict(kinds), "sections", len(b.sections), "chunks", chunks)
print("leaflet sections/doc p50", sorted(per_doc.values())[len(per_doc)//2], "max", max(per_doc.values()))
EOF
```
Expected: `documents` vẫn 3.120 (689 + 25 + 2.406), section leaflet khoảng 2.406 × 16 ≈ 38.000, chunk tổng khoảng 27.000 đến 30.000, p50 section mỗi tờ 15 đến 17. Nếu số document leaflet khác 2.406 thì Task 2 gom sai, dừng lại.

- [ ] **Step 3: Commit manifest và report**

```bash
git add pharma-lab/data/corpus/rag-final/manifest.json pharma-lab/data/corpus/rag-final/validation_report.json pharma-lab/data/corpus/formulary/manifest.json
git commit -m "data: rebuild corpus with leaflets split by heading"
```

---

### Task 5: Remap bộ golden sang section con và bỏ hậu tố

**Files:**
- Create: `pharma-lab/src/pharma_lab/e2e/golden_remap.py`
- Modify: `pharma-lab/src/pharma_lab/cli/commands/e2e.py` (lệnh `golden remap`)
- Modify: `pharma-lab/data/evaluation/e2e/authoring/*.authored.jsonl` (bằng lệnh), `pharma-lab/docs/guides/e2e-golden-authoring.md`
- Test: `pharma-lab/tests/e2e/test_golden_remap.py` (mới)

**Interfaces:**
- Consumes: `CorpusText` (`sections`, `section_documents`), `chunk_texts(bundle, section_ids)`, `GoldenItem`.
- Produces: `remap_item(item: GoldenItem, corpus: CorpusText, chunks: Callable[[Iterable[str]], dict[str, str]]) -> RemapResult(item: GoldenItem, notes: list[str])`; `strip_hint(text: str) -> str`; CLI `uv run pharma-lab e2e golden remap --bundle data/corpus/formulary` ghi lại từng file authoring và `authoring/remap.todo.md`.

- [ ] **Step 1: Test thất bại**

```python
# pharma-lab/tests/e2e/test_golden_remap.py
from pharma_lab.e2e.corpus_text import CorpusText
from pharma_lab.e2e.golden import GoldenItem
from pharma_lab.e2e.golden_remap import remap_item, strip_hint

PAGE = "leaflet:t:pramital-20"
PRECAUTION = f"{PAGE}:05-luu-y"
PREGNANCY = f"{PAGE}:06-thai-ky-va-cho-con-bu"
CORPUS = CorpusText(
    sections={
        PRECAUTION: "# Pramital 20 mg\n\n### 5. Lưu ý\n\nTheo dõi ý định tự sát.",
        PREGNANCY: "# Pramital 20 mg\n\n### 6. Thai kỳ và cho con bú\n\nKhông dùng trong ba tháng đầu.",
    },
    section_documents={PRECAUTION: PAGE, PREGNANCY: PAGE},
    titles={PAGE: "Pramital 20 mg trị trầm cảm (2 vỉ x 14 viên)"},
)


def _chunks(section_ids):
    return {f"{sid}:chunk-001": CORPUS.sections[sid] for sid in section_ids}


def _item(**changes):
    data = {
        "item_id": "e2e-ans-0001",
        "category": "answerable",
        "source_query_id": "q",
        "turns": [
            {
                "role": "user",
                "text": "Khi dùng Pramital 20 mg trị trầm cảm (2 vỉ x 14 viên) cần lưu ý gì? (phần thai kỳ và cho con bú)",
            }
        ],
        "expected_behavior": "grounded",
        "gold_section_ids": [PAGE],
        "gold_chunk_ids": [f"{PAGE}:chunk-003"],
        "reference": {
            "answer": "Không dùng trong ba tháng đầu.",
            "key_facts": [
                {
                    "fact": "Không dùng ba tháng đầu",
                    "evidence_quote": "Không dùng trong ba tháng đầu.",
                    "section_id": PAGE,
                }
            ],
        },
        "eval_group": "patient_natural",
    }
    data.update(changes)
    return GoldenItem.model_validate(data)


def test_strip_hint_removes_trailing_phan_suffix_only() -> None:
    assert strip_hint("A cần lưu ý gì? (phần thai kỳ)") == "A cần lưu ý gì?"
    assert (
        strip_hint("Fordia 850 mg (10 vỉ x 10 viên) dùng liều thế nào?")
        == "Fordia 850 mg (10 vỉ x 10 viên) dùng liều thế nào?"
    )


def test_remap_moves_gold_ids_to_the_subsection_holding_the_quote() -> None:
    result = remap_item(_item(), CORPUS, _chunks)
    item = result.item
    assert item.gold_section_ids == [PREGNANCY]
    assert item.gold_chunk_ids == [f"{PREGNANCY}:chunk-001"]
    assert item.reference.key_facts[0].section_id == PREGNANCY
    assert item.eval_group == "leaflet_short"
    assert (
        item.turns[-1].text
        == "Khi dùng Pramital 20 mg trị trầm cảm (2 vỉ x 14 viên) cần lưu ý gì?"
    )
    assert any("hint removed" in note for note in result.notes)


def test_remap_reports_quotes_found_in_several_subsections() -> None:
    corpus = CorpusText(
        sections={
            **CORPUS.sections,
            PRECAUTION: CORPUS.sections[PRECAUTION]
            + "\n\nKhông dùng trong ba tháng đầu.",
        },
        section_documents=CORPUS.section_documents,
        titles=CORPUS.titles,
    )
    result = remap_item(_item(), corpus, _chunks)
    assert any("ambiguous" in note for note in result.notes)
    assert result.item.gold_section_ids == [PRECAUTION, PREGNANCY]
```

- [ ] **Step 2: Chạy test để thấy thất bại**

Run: `cd pharma-lab && uv run pytest tests/e2e/test_golden_remap.py -q`
Expected: FAIL, `ModuleNotFoundError: pharma_lab.e2e.golden_remap`.

- [ ] **Step 3: Cài module remap**

```python
# pharma-lab/src/pharma_lab/e2e/golden_remap.py
"""Carry authored golden items over to the corpus whose leaflets are split by heading."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from pharma_lab.e2e.corpus_text import CorpusText, normalize_space
from pharma_lab.e2e.golden import GoldenItem

GROUP_RENAMES = {"patient_natural": "leaflet_short", "noisy_confuser": "noisy"}
_HINT = re.compile(r"\s*\((?:phần|Phần)\s[^()]*\)\s*$")
ChunkLookup = Callable[[Iterable[str]], dict[str, str]]


@dataclass(frozen=True)
class RemapResult:
    item: GoldenItem
    notes: list[str]


def strip_hint(text: str) -> str:
    return _HINT.sub("", text).strip()


def _subsections(corpus: CorpusText, page_or_section: str) -> list[str]:
    if page_or_section in corpus.sections:
        return [page_or_section]
    return sorted(
        key
        for key, document in corpus.section_documents.items()
        if document == page_or_section
    )


def _holders(corpus: CorpusText, candidates: list[str], quote: str) -> list[str]:
    needle = normalize_space(quote)
    return [
        key for key in candidates if needle in (corpus.normalized_section(key) or "")
    ]


def remap_item(
    item: GoldenItem, corpus: CorpusText, chunks: ChunkLookup
) -> RemapResult:
    notes: list[str] = []
    data = item.model_dump(mode="json")
    data["eval_group"] = GROUP_RENAMES.get(
        data.get("eval_group") or "", data.get("eval_group")
    )
    last = data["turns"][-1]["text"]
    stripped = strip_hint(last)
    if stripped != last:
        data["turns"][-1]["text"] = stripped
        notes.append(f"{item.item_id}: hint removed from question")
    gold: list[str] = []
    for fact in data["reference"]["key_facts"]:
        candidates = _subsections(corpus, fact["section_id"])
        holders = _holders(corpus, candidates, fact["evidence_quote"])
        if not holders:
            notes.append(
                f"{item.item_id}: quote not found: {fact['evidence_quote'][:60]}"
            )
            continue
        if len(holders) > 1:
            notes.append(f"{item.item_id}: ambiguous quote in {holders}")
            gold.extend(key for key in holders if key not in gold)
        else:
            gold.extend(key for key in holders if key not in gold)
        fact["section_id"] = holders[0] if len(holders) == 1 else fact["section_id"]
    if gold:
        data["gold_section_ids"] = gold
        texts = chunks(gold)
        data["gold_chunk_ids"] = sorted(
            label
            for label, text in texts.items()
            if any(
                normalize_space(f["evidence_quote"]) in normalize_space(text)
                for f in data["reference"]["key_facts"]
            )
        )
    return RemapResult(GoldenItem.model_validate(data), notes)


def remap_files(
    paths: Iterable[Path], corpus: CorpusText, chunks: ChunkLookup, todo: Path
) -> int:
    notes: list[str] = []
    changed = 0
    for path in paths:
        lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        out: list[str] = []
        for line in lines:
            result = remap_item(
                GoldenItem.model_validate(json.loads(line)), corpus, chunks
            )
            notes.extend(result.notes)
            dumped = json.dumps(result.item.model_dump(mode="json"), ensure_ascii=False)
            changed += dumped != line
            out.append(dumped)
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    todo.write_text(
        "# Golden remap notes\n\n" + "\n".join(f"- {note}" for note in notes) + "\n",
        encoding="utf-8",
    )
    return changed
```

Với item mơ hồ (`len(holders) > 1`), `fact.section_id` giữ nguyên key trang và `gold_section_ids` gồm mọi holder; `golden check` sẽ báo "key fact cites ... which is not a gold section" cho các item đó, và ghi chú trong todo cho tác giả chọn tay. Test thứ ba ở Step 1 kỳ vọng `gold_section_ids == [PRECAUTION, PREGNANCY]`, khớp.

Lệnh CLI trong `cli/commands/e2e.py`, cạnh `golden_check`:

```python
@golden_app.command("remap")
def golden_remap(
    ctx: typer.Context,
    bundle: Annotated[Path, typer.Option("--bundle", file_okay=False)] = BUNDLE_DIR,
    authoring_dir: Annotated[Path, typer.Option("--authoring-dir")] = E2E_AUTHORING_DIR,
) -> None:
    def run() -> CommandResult:
        knowledge = read_bundle(bundle)
        corpus = corpus_text(knowledge)
        paths = sorted(authoring_dir.glob("*.authored.jsonl"))
        changed = remap_files(
            paths,
            corpus,
            lambda ids: chunk_texts(knowledge, ids),
            authoring_dir / "remap.todo.md",
        )
        return CommandResult(
            command="e2e golden remap",
            status=CommandStatus.COMPLETE,
            artifact=authoring_dir / "remap.todo.md",
            details={"changed": changed, "files": len(paths)},
        )

    run_handler(state_from_context(ctx), run)
```

(`E2E_AUTHORING_DIR` đã có trong `pharma_lab.config.paths`; `corpus_text`, `chunk_texts` import từ `pharma_lab.e2e.corpus_text`, `remap_files` từ `pharma_lab.e2e.golden_remap`.)

- [ ] **Step 4: Chạy test**

Run: `cd pharma-lab && uv run pytest tests/e2e/test_golden_remap.py -q`
Expected: 3 passed.

- [ ] **Step 5: Chạy remap trên dữ liệu thật và build golden**

```bash
cd pharma-lab
uv run pharma-lab e2e golden remap --bundle data/corpus/formulary
cat data/evaluation/e2e/authoring/remap.todo.md | head -80
uv run pharma-lab e2e golden build
```
Expected: `remap.todo.md` liệt kê khoảng 50 dòng "hint removed" và ít dòng "ambiguous" hoặc "quote not found". Với mỗi dòng ambiguous hoặc not found, mở item trong file authoring, chọn section con đúng theo intent câu hỏi, sửa `section_id` của key fact và `gold_section_ids`, chạy lại `golden check` trên file đó. 50 câu bị bỏ hậu tố: đọc lại từng câu; câu nào sau khi bỏ hậu tố không còn nêu đủ chủ đề của key fact (ví dụ "cần lưu ý gì?" nhưng fact về thai kỳ) thì viết lại câu cho tự nhiên, ví dụ "Khi dùng Pramital 20 mg lúc mang thai hoặc cho con bú cần lưu ý gì?". `golden build` phải thành công với 500 item và nhóm `leaflet_short`, `noisy`.

- [ ] **Step 6: Lint, type, test, commit**

```bash
cd pharma-lab && uv run ruff check src tests && uv run ruff format src tests && uv run pyrefly check --min-severity warn && uv run pytest -q
git add pharma-lab/src/pharma_lab/e2e/golden_remap.py pharma-lab/src/pharma_lab/cli/commands/e2e.py pharma-lab/tests/e2e/test_golden_remap.py pharma-lab/data/evaluation/e2e/authoring pharma-lab/data/evaluation/e2e/golden_e2e.manifest.json
git commit -m "feat(pharma-lab): remap the golden set to leaflet subsections and drop question hints"
```

---

### Task 6: Sinh benchmark mới và nhãn relevance, kiểm tra không rò rỉ

**Files:**
- Chạy lệnh; sửa `pharma-lab/docs/guides/evaluation.md:103` và `cli-reference.md:82` (tên nhóm).

- [ ] **Step 1: Sinh benchmark**

```bash
cd pharma-lab
uv run pharma-lab evaluation build --bundle data/corpus/formulary
```
Expected: `evaluation build` hoàn tất với 10.000 dòng và judgments được ghi.

- [ ] **Step 2: Kiểm tra rò rỉ và phân bố**

```bash
uv run python - <<'EOF'
import json, collections
rows = [json.loads(l) for l in open("data/evaluation/gold/section_retrieval_eval.jsonl")]
assert len(rows) == 10000
assert not any("(phần" in r["query"] for r in rows), "hint suffix still present"
assert not any(" [" in r["query"] or " #" in r["query"] for r in rows), "unique_query suffix present"
assert "difficulty" not in rows[0]
print(collections.Counter(r["eval_group"] for r in rows))
print(collections.Counter(r["query_form"] for r in rows))
print(collections.Counter(r["intent_category"] for r in rows).most_common(20))
print("any_acceptable", sum(r["answer_mode"] == "any_acceptable" for r in rows))
leaf = [r for r in rows if r["eval_group"] == "leaflet"]
print("leaflet queries containing a full marketing title:", sum(len(r["query"]) > 110 for r in leaf))
EOF
```
Expected: sáu nhóm đúng quota; `query_form` có `typo` 200 và `noisy` 300, không có `confuser`, `patient`; `general_info` dưới 1.500 và `overdose`, `storage`, `pharmacology` mỗi loại vài trăm; không câu nào mang hậu tố.

- [ ] **Step 3: Đọc mẫu**

```bash
uv run python - <<'EOF'
import json, random
random.seed(1)
rows = [json.loads(l) for l in open("data/evaluation/gold/section_retrieval_eval.jsonl")]
for form in sorted({r["query_form"] for r in rows}):
    sample = random.sample([r for r in rows if r["query_form"] == form], 4)
    print("==", form)
    for r in sample: print("  ", r["query"], "||", r["expected_section_ids"][0].split(":")[-1])
EOF
```
Đọc từng dạng; câu nào vẫn lộ đáp án hoặc không phải câu hỏi thì sửa template tương ứng trong Task 3 và chạy lại Step 1.

- [ ] **Step 4: Cập nhật docs và commit**

Sửa `docs/guides/evaluation.md` dòng về mẫu 10 % và `cli-reference.md` dòng `--sample`: `50 leaflet_short, 50 noisy` thay cho `patient_natural`, `noisy_confuser`.

```bash
git add pharma-lab/docs/guides/evaluation.md pharma-lab/docs/guides/cli-reference.md pharma-lab/data/evaluation/gold/section_retrieval_eval.judgments.manifest.json
git commit -m "data: regenerate the retrieval benchmark without question hints"
```

(`section_retrieval_eval.jsonl` và `judgments.jsonl` đi qua `data push`, không vào git; kiểm tra `git status` không có file lớn.)

---

### Task 7: Embedding, import và chạy lại bảng retrieval trên release mới

**Files:**
- Chạy lệnh trong tmux; commit `run.json`, `report.md`, `metrics.jsonl` của các run mới.

**Interfaces:**
- Consumes: bundle mới, benchmark mới, stack `vipharmind-eval` (`docs/guides/evaluation.md` §2).
- Produces: run `bm25-v2-k30`, `dense-<model>-v2-k30` cho năm model, `hybrid-qwen4b-v2-p50-k30-rrf2`, `hybrid-qwen4b-v2-p50-k30-rrf60`, rerank bốn model trên run hybrid rrf2 và Qwen3-Reranker-4B trên run dense 4B.

- [ ] **Step 0: Model Q8_0 và profile Kaggle**

Theo spec §2.1b mọi model tự host ở Q8_0, tải bản Q8_0 đã công bố theo commit và kiểm sha256
(không tự quantize); reranker Qwen3 đổi template rerank sang tiếng Việt y tế bằng
`gguf-new-metadata` như `docs/guides/evaluation.md`. Ghi size và sha256 vào `runtime/catalog.py`,
đổi tên catalog sang hậu tố `-q8_0`, xoá file F16, cache embedding, rerank và profile F16, và
dataset Kaggle `vector-cache-gguf-*` cũ.
Topology mọi model là replicated 2×1; nới không gian tìm profile cho các model 4B và 9B vì VRAM
dư. Cache embedding F16 xoá. Chạy benchmark profile trước khi embed thật, ba tài khoản song song:

```bash
cd pharma-lab
uv run pharma-lab bundle embed --bundle data/corpus/formulary --backend kaggle --model qwen3-embedding:4b-q8_0 --kaggle-account acc1 --benchmark
uv run pharma-lab rerank --run hybrid-qwen4b-v2-p50-k30-rrf2 --backend kaggle --model qwen3-reranker:4b-q8_0 --kaggle-account acc2 --benchmark
```
Expected: profile Q8_0 của từng model trong `data/work` và trên dataset profile Kaggle; mọi model
sau đó dùng profile này.

- [ ] **Step 1: Embed corpus trên Kaggle cho năm model**

```bash
cd pharma-lab
for m in qwen3-embedding:4b-q8_0 qwen3-embedding:8b-q8_0 qwen3-embedding:0.6b-q8_0 bge-m3:567m-q8_0 embeddinggemma:300m-q8_0; do
  uv run pharma-lab bundle embed --bundle data/corpus/formulary --backend kaggle --model "$m" --kaggle-account auto
done
```
Expected: `embeddings/<slug>.jsonl` cho năm model trong bundle; model Q8_0 chưa có cache nên embed toàn bộ corpus, chia mỗi model một tài khoản.

- [ ] **Step 2: Stack đánh giá và import mỗi model**

```bash
cd /home/andv/personal/vipharmind
POSTGRES_PORT=5434 QDRANT_HTTP_PORT=6335 docker compose -p vipharmind-eval up -d --wait postgres qdrant
export PHARMA_POSTGRES__DSN=postgresql+psycopg://vipharmind:vipharmind@localhost:5434/vipharmind
export PHARMA_QDRANT__URL=http://localhost:6335
cd backend && uv run pharma-agent migrate
```
Với mỗi model (bảng trong `evaluation.md` §3, chiều vector và alias `eval_<slug>`):
```bash
export PHARMA_RETRIEVAL__EMBEDDING__MODEL=qwen3-embedding:4b-q8_0
export PHARMA_RETRIEVAL__EMBEDDING__DIMENSION=2560
export PHARMA_RETRIEVAL__QDRANT_COLLECTION=eval_qwen3_embedding_4b_q8_0
uv run pharma-agent corpus import ../pharma-lab/data/corpus/formulary --collection formulary --publish
```
Expected: mỗi import tạo release mới; `uv run pharma-agent corpus releases --collection formulary` liệt kê release đang publish.

- [ ] **Step 3: Embed query và retrieve**

```bash
cd pharma-lab
for m in qwen3-embedding:4b-q8_0 qwen3-embedding:8b-q8_0 qwen3-embedding:0.6b-q8_0 bge-m3:567m-q8_0 embeddinggemma:300m-q8_0; do
  uv run pharma-lab embed queries --backend kaggle --model "$m" --kaggle-account auto
done
# với PHARMA_RETRIEVAL__* trỏ vào Qwen3-Embedding-4B:
uv run pharma-lab retrieve --run bm25-v2-k30 --retriever bm25 --candidate-k 30
uv run pharma-lab retrieve --run dense-qwen4b-v2-k30 --retriever dense --candidate-k 30
uv run pharma-lab retrieve --run hybrid-qwen4b-v2-p50-k30-rrf2 --retriever hybrid --prefetch-k 50 --candidate-k 30 --rrf-k 2
uv run pharma-lab retrieve --run hybrid-qwen4b-v2-p50-k30-rrf60 --retriever hybrid --prefetch-k 50 --candidate-k 30 --rrf-k 60
# đổi PHARMA_RETRIEVAL__* sang từng model còn lại rồi:
uv run pharma-lab retrieve --run dense-qwen8b-v2-k30 --retriever dense --candidate-k 30
uv run pharma-lab retrieve --run dense-qwen06b-v2-k30 --retriever dense --candidate-k 30
uv run pharma-lab retrieve --run dense-bge-m3-v2-k30 --retriever dense --candidate-k 30
uv run pharma-lab retrieve --run dense-gemma300m-v2-k30 --retriever dense --candidate-k 30
for r in bm25-v2-k30 dense-qwen4b-v2-k30 hybrid-qwen4b-v2-p50-k30-rrf2 hybrid-qwen4b-v2-p50-k30-rrf60 dense-qwen8b-v2-k30 dense-qwen06b-v2-k30 dense-bge-m3-v2-k30 dense-gemma300m-v2-k30; do
  uv run pharma-lab metrics --run "$r" --top-k 30
done
```
Expected: mỗi run có `reports/baseline/top30-window3/report.md`. Ghi Hit@10 và nDCG@10 của hybrid rrf2 và dense 4B vào ghi chú so với v1 (95,9 % và 95,4 % Hit@10).

- [ ] **Step 4: Rerank**

```bash
for m in qwen3-reranker:4b-q8_0 qwen3-reranker:8b-q8_0 qwen3-reranker:0.6b-q8_0 bge-reranker-v2-m3:q8_0; do
  uv run pharma-lab rerank --run hybrid-qwen4b-v2-p50-k30-rrf2 --backend kaggle --model "$m" --kaggle-account auto
  uv run pharma-lab metrics --run hybrid-qwen4b-v2-p50-k30-rrf2 --model "$m" --top-k 30
done
uv run pharma-lab rerank --run dense-qwen4b-v2-k30 --backend kaggle --model qwen3-reranker:4b-q8_0 --kaggle-account auto
uv run pharma-lab metrics --run dense-qwen4b-v2-k30 --model qwen3-reranker:4b-q8_0 --top-k 30
```
Tên model reranker lấy đúng theo catalog (`uv run pharma-lab rerank --help` và `runtime/catalog.py`); v1 dùng biến thể `-vimed` cho Qwen3 reranker với instruction tiếng Việt y tế, giữ đúng biến thể v1 đã báo trong bài (xem `data/evaluation/runs/hybrid-qwen4b-p50-k30-rrf2/run.json` mục `rerank_variants`).

Expected: `reports/rerank/<slug>/top30-window3/report.md` cho bốn reranker và cho dense + 4B. Đây là hàng D1 của spec.

- [ ] **Step 5: Lưu archive và commit**

```bash
uv run pharma-lab data push --kaggle-account acc1 --message "Paper v2 data phase: leaflet subsections, leak-free benchmark, v2 retrieval runs"
cd /home/andv/personal/vipharmind
git add pharma-lab/data/evaluation/runs/*-v2-*/run.json pharma-lab/data/evaluation/runs/*-v2-*/reports
git commit -m "data: retrieval runs on the v2 release and benchmark"
```

---

### Task 7b: Tập "cần tra nhiều lượt" trong golden 500 câu

Theo spec §3.0b. Phụ thuộc Task 7 (retrieval trên release mới). Các bước, mỗi bước TDD như các task
mã ở trên:

1. `golden.py`: thêm `Category.MULTI_HOP` (behavior grounded, prefix `e2e-mhop-`), `QUOTAS` thành
   answerable 270, multi_hop 150, multi_turn 50, ba nhóm an toàn 10; `ANSWERABLE_PER_GROUP = 45`.
   Test: quota và validate cho item multi_hop.
2. Lệnh `e2e golden hard-candidates --run <retrieval run> --top-k 8`: đọc candidates của run
   hybrid + rerank, liệt kê câu benchmark mà top-k thiếu section gold, gán một trong bốn loại theo
   `answer_mode`, `eval_group` và số thuốc; ghi `authoring/multi-hop.todo.jsonl`. Câu hai thuốc và
   biệt dược sang hoạt chất sinh thêm bằng luật từ cặp section (relevance judgments đã có ánh xạ
   leaflet sang hoạt chất). Test trên fixture nhỏ.
3. Lệnh `e2e golden trim --per-group 45`: bỏ 150 câu answerable mà run một lượt phủ đủ gold, đều
   theo nhóm. Test.
4. Soạn 150 item: bản nháp key fact bằng LLM qua proxy (gemini-3.1-flash-lite) với quote nguyên
   văn từ section gold, `golden check`, tác giả và dược sĩ duyệt; `golden build` ra 500 item.
5. `AnswerRecord.rounds`: evidence section ids sau mỗi vòng search; report thêm
   `gold_coverage_round1`, `gold_coverage_final`, `rounds_used`, `rescued_rate`, chia theo category.
   Test với executor giả.

### Task 8: Ghi lại kết quả pha D cho bài và các pha sau

**Files:**
- Create: `docs/research/paper-v2/08-phase-d-results.md`
- Modify: `pharma-lab/docs/guides/e2e-golden-authoring.md` (lệnh `golden remap`), `pharma-lab/data/README.md` nếu tên file đổi (không đổi)

- [ ] **Step 1: Viết bảng so sánh v1 và v2**

Từ `report.md` của các run v1 (`hybrid-qwen4b-p50-k30-rrf2`, rerank 4B) và v2, lập bảng Hit@3/5/10, nDCG@10, MRR@10 cho toàn bộ và theo nhóm, cộng số liệu corpus mới (section, chunk, p50 chunk). Ghi rõ ba nguyên nhân thay đổi: bỏ hậu tố, gold leaflet thu về section con, nhóm đổi tên. Mục này là nguồn cho đoạn "so với v1" trong bài (spec §3.0).

- [ ] **Step 2: Cập nhật guide authoring**

Thêm vào `e2e-golden-authoring.md` sau dòng `golden check`: `uv run pharma-lab e2e golden remap --bundle data/corpus/formulary   # khi corpus đổi key section: dời gold id theo quote, ghi authoring/remap.todo.md`.

- [ ] **Step 3: Commit**

```bash
git add docs/research/paper-v2/08-phase-d-results.md pharma-lab/docs/guides/e2e-golden-authoring.md
git commit -m "docs: record phase D results and the golden remap command"
```

---

## Self-review

- **Spec coverage (§3.0):** tách leaflet theo heading (Task 1, 2, 4); bỏ hậu tố và đáp án trong ngoặc (Task 3 b, d, Task 6 kiểm tra); chunk_coverage hỏi theo intent của heading (Task 3 b và c, vì section con mang heading); tên sản phẩm chuẩn hóa (Task 3 c); đổi tên patient_natural, bỏ confuser, typo tự động, bỏ difficulty, tách general_info, any_acceptable cho chunk trùng (Task 3); golden chỉ viết lại 50 item có hậu tố và remap section (Task 5); chạy lại bảng retrieval với năm embedding và bốn reranker, bỏ BGE-gemma (Task 7); đoạn "so với v1" (Task 8). Embedding chạy trên Kaggle chứ không qua API như spec viết, vì `bundle embed` không có backend API và kết quả cần so sánh được với v1; sửa một dòng ở spec §3.0 khi plan được duyệt. OpenAI text-embedding-3-large của v1 là run nhập từ pipeline cũ (`origin: imported`) nên không chạy lại; bài v2 bỏ hàng đó.
- **Placeholder:** không còn "TBD"; mọi bước mã có code; các lệnh có tham số cụ thể.
- **Type consistency:** `integrate_drug_file` trả `tuple[list[dict], list[dict]]` dùng ở Task 1 và 2 qua `page_id`; `unique_query(query, seen)` dùng thống nhất; `typo_query(query, seed)`; `remap_item(item, corpus, chunks)` với `chunks: Callable[[Iterable[str]], dict[str, str]]` khớp `chunk_texts(bundle, ids)`.
- **Review Focus:** 1 và 2 có test ở Task 1 (không heading, heading lặp); 3 có test `unique_query` ở Task 3; 4 có test "ambiguous" ở Task 5; 5 có test `typo_query` giữ "500 mg" ở Task 3.
