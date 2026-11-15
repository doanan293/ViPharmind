# Corpus, pipeline dữ liệu và rerank

Ngày: 2026-11-15. Mô tả mã trên nhánh `v2.0.0` (commit `9732e8e`). Spec này gộp và thay cho 12
file spec, plan của corpus platform, seed-pipeline, chuẩn hoá dữ liệu seed và rerank native
(9/2026). Nguồn gốc từng quyết định ở mục 5.

## 1. Mục tiêu và phạm vi

Mục tiêu:

1. Mỗi chunk của corpus có danh tính bền vững và nội dung bất biến, để citation luôn trỏ đúng đoạn
   văn mà câu trả lời đã dựa vào, kể cả sau khi build lại corpus.
2. Postgres (schema `corpus`) là nguồn chính của corpus. Qdrant chỉ là index dẫn xuất.
3. Backend `pharma-agent` giữ mọi năng lực corpus lúc chạy: bundle, chia chunk, import, release,
   index, đọc corpus khi retrieval. `pharma-lab` là công cụ offline tạo dữ liệu gốc và chạy đánh
   giá; nó bàn giao bằng knowledge bundle và không ghi thẳng vào Postgres hay Qdrant.
4. Corpus hệ thống (`formulary`: Dược thư Quốc gia Việt Nam và tờ hướng dẫn sử dụng thuốc) và corpus
   người dùng tự soạn đi qua cùng một đường import.
5. Reranker chỉ có một protocol (`native_rerank`, `POST /v1/rerank`), dùng chung cho agent và đánh
   giá.

Phạm vi:

- `backend/src/pharma_agent/domain/corpus/`, `application/corpus/` (phần import, release, index),
  `infrastructure/persistence/postgres/corpus_*`, `infrastructure/retrieval/qdrant_index.py`,
  `qdrant_adapter.py`, `postgres_corpus.py`, `llama_cpp_reranker.py`, `rerankers.py`, nhóm lệnh
  `pharma-agent corpus`.
- `pharma-lab/`: nguồn dữ liệu, build `rag-final`, export và embed bundle, bố cục `data/`, archive
  dữ liệu, catalog model và cấu hình server reranker.
- `compose.local-models.yaml` (server embedding và reranker trên CPU).

## 2. Ranh giới và luồng dữ liệu

```text
pharma-lab source crawl     sitemap -> data/sources/leaflets/ (html, danh sách URL, manifest)
pharma-lab build            PDF Dược thư + HTML tờ hướng dẫn -> data/corpus/rag-final/ (sections + blocks)
pharma-lab validate         kiểm contract rag-final-v3
pharma-lab bundle export    rag-final -> data/corpus/formulary/ (knowledge-bundle/v1)
pharma-lab bundle embed     chunk_document của backend -> embeddings/<model_slug>.jsonl (Kaggle hoặc local)
pharma-lab bundle rechunk   bản sao bundle với chunking khác (thí nghiệm D2, D7)
pharma-agent corpus import  bundle -> release mới trong schema corpus + point Qdrant
```

- `pharma-lab` khai báo `pharma-agent` là dependency trong uv workspace và chỉ dùng mặt công khai
  của backend. Danh sách module được dùng nằm trong `pharma-lab/tests/test_backend_public_api.py`;
  phần corpus gồm `pharma_agent.domain.corpus.{bundle,identity,chunking,enrichment}` và
  `pharma_agent.infrastructure.composition`. Backend không import `pharma_lab`.
- Import-linter ép ranh giới: `pharma_lab` không import `pharma_agent.api` hay
  `pharma_agent.infrastructure.persistence`. Worker Kaggle (`integrations/kaggle/workers/`) không
  import backend, vì mã worker chạy trên kernel không có workspace. Kernel embed chỉ nhận text và
  hash.
- Backend là chunker duy nhất. `pharma-lab` gọi `chunk_document` để có `embedding_text` khi embed
  bundle và để sinh chunk đánh giá, nên chunk lúc đánh giá trùng chunk lúc chạy.

## 3. Thiết kế hiện hành: backend

### 3.1 Knowledge bundle `knowledge-bundle/v1`

Model, đọc ghi và validate nằm trong `domain/corpus/bundle.py`. Hai phía dùng cùng một bộ kiểm.

```text
bundle/
  manifest.json
  documents.jsonl
  sections.jsonl
  glossary.json
  colloquial_mappings.json
  embeddings/<model_slug>.jsonl      tuỳ chọn, mỗi model một file
```

| File | Nội dung |
| --- | --- |
| `manifest.json` | `schema_version`, `collection {key, title}`, `generator {name, version, build_id}`, `source_digests`, số document và section, `files {tên: {sha256, bytes}}`, `embeddings [{model, dims, file}]`, `chunking {target_chars, max_chars, enrichment}` |
| `documents.jsonl` | `{key, kind, title, source {title, url}, attributes}`; `kind ∈ {drug_monograph, general_monograph, leaflet}` |
| `sections.jsonl` | `{key, document_key, heading, context_path[], ordinal, start_page, end_page, blocks[]}` |
| `blocks[]` | `{kind, markdown, start_page, end_page, table_key}`; `kind ∈ {prose, table, list, index_entries}` quyết định cách cắt một mục dài |
| `glossary.json` | Mảng `GlossaryEntry` (term, mở rộng tiếng Việt và tiếng Anh, alias, category) |
| `colloquial_mappings.json` | Mảng `{key, aliases[], visual_sign, product_names[], section_keys[]}` |
| `embeddings/<model_slug>.jsonl` | `{embedding_text_sha256, dims, vector}`; vector float32 little-endian mã hoá base64 |

- Key document: `drug:<slug>`, `general:<slug>`, `leaflet:<nhóm>:<slug>`. Key section trùng
  `section_id` của `rag-final`, nên gold của benchmark tiếp tục dùng được.
- Tờ hướng dẫn có `source.title = "Tờ hướng dẫn sử dụng"` và `source.url = null`. Tên và URL của
  website nguồn chỉ nằm trong `pharma-lab/data/sources/leaflets/manifest.json`, không vào bundle,
  DB, API hay prompt.
- `chunking` mặc định `target_chars = 4200`, `max_chars = 5600`, `enrichment = true`. Trường
  `enrichment` bị bỏ khỏi manifest khi bằng `true`, nên bundle cũ giữ nguyên digest.
- Validate (`read_bundle`, `write_bundle`): schema version, sha256 và kích thước từng file, key duy
  nhất, `document_key` tồn tại, `ordinal` không trùng, block không rỗng, trang hợp lệ, độ dài vector
  bằng `dims × 4` byte. Lỗi liệt kê đủ vị trí (file, dòng, field) và import dừng trước khi ghi.
- File embedding được đọc và ghi theo từng dòng (`read_bundle_embeddings`,
  `write_bundle_embeddings`); bộ nhớ chỉ giữ vector của một model. Manifest được thay nguyên tử
  dưới file lock.

### 3.2 Chunker và danh tính

`domain/corpus/chunking.py`, `CHUNKER_VERSION = "chunker-v2"`.

- `chunk_document` gộp các mục liền kề của cùng một tài liệu theo thứ tự: thêm mục kế tiếp chừng
  nào tổng còn dưới `target_chars`. Mục dài hơn `max_chars` được cắt riêng theo `kind` của block
  (bảng lặp lại hai dòng đầu, danh sách cắt theo dòng không vỡ mục, prose cắt theo đoạn rồi câu),
  rồi các mảnh được gói lại tới `max_chars`. Không gộp qua tài liệu khác.
- Chunk là đúng văn bản LLM đọc; không còn hydrate. Text chunk giữ `## <heading>` của từng mục;
  `context_header` là `<tiêu đề> > <heading 1>; <heading 2>; ...`.
- `embedding_text` = header, tên colloquial chưa xuất hiện, chunk text, phần mở rộng thuật ngữ
  (`compose_embedding_text` trong `enrichment.py`). Với `enrichment = false` chỉ còn chunk text.
- Trên `formulary` hiện tại: 13.412 chunk, trung bình khoảng 1.000 token Qwen3, dài nhất khoảng
  3.100 token. Slot embed và ubatch reranker vì vậy là 4.096 token.
- `chunk_version_id = uuid5(NS, "chunk\x1f" + sha256(document_id, section_keys, chunk_text,
  embedding_text, CHUNKER_VERSION))`, với `NS = uuid5(NAMESPACE_URL, "pharma-agent:corpus:v1")`.
  `document_id` đã gắn collection, nên cùng một tài liệu ở hai collection là hai dòng riêng.
  `embedding_text` nằm trong id, nên đổi glossary hay colloquial mapping sinh chunk version mới và
  vector không bao giờ lệch text.
- `collection_id`, `document_id`, `section_id` là uuid5 tất định theo key. Release id là `uuid4`.
- Đổi thuật toán chia chunk thì tăng `CHUNKER_VERSION`; import lại tạo release mới.

### 3.3 Schema `corpus` (Postgres)

Migration hiện hành: `0005` (tạo schema), `0012`, `0016`, `0018`–`0021`.

| Bảng | Cột chính | Ghi chú |
| --- | --- | --- |
| `collections` | `id, key, title, owner_user_id, owner_organization_id, visibility, current_release_id, deleted_at` | `visibility ∈ {private, organization, public}`; xoá mềm. Chủ sở hữu và quyền thấy thuộc spec `product-accounts-orgs` |
| `documents` | `id, collection_id, key, title, source_title` | unique `(collection_id, key)` |
| `sections` | `id, document_id, key, heading` | danh tính lâu dài của mục |
| `chunk_versions` | `id, document_id, ordinal, section_keys[], headings[], chunk_text, context_header, embedding_text_sha256, start_page, end_page, term_annotations, colloquial, chunker_version` | bất biến; không lưu `embedding_text` (dựng lại từ các cột khi cần) |
| `releases` | `id, collection_id, number, status, bundle_digest, chunker_version, embedding_model, stats, created_at, ready_at, published_at, retired_at` | `status ∈ {building, ready, retired}` |
| `release_chunks` | `release_id, chunk_version_id, document_id, ordinal` | chunk nào thuộc release nào |
| `source_documents`, `glossary_entries`, `colloquial_mappings`, `ingest_jobs` | nội dung người dùng soạn và job xuất bản (mục 3.6) | |

- Release hiện hành của collection là `collections.current_release_id`; `published_at` dùng cho
  rollback.
- `message_citations` (schema `public`) tham chiếu `corpus.chunk_versions` bằng FK `RESTRICT`, nên
  `gc` không xoá được chunk đang được trích dẫn. Citation lưu tham chiếu, không lưu bản sao text.
- Không có bảng embedding cache và không lưu vector trong Postgres. Vector nằm trong bundle và Qdrant.

### 3.4 Import, release và dọn dẹp

`ImportKnowledgeBundle` (`application/corpus/import_bundle.py`) là đường ingest duy nhất.

1. `read_bundle` validate ở biên (CLI hoặc job xuất bản). `corpus import --collection` phải trùng
   `manifest.collection.key`, sai thì thoát mã 2.
2. `build_snapshot` dựng toàn bộ hàng (document, section, chunk version, release chunk) bằng chunker
   và hàm danh tính, trước khi chạm storage.
3. Bộ ba (`bundle_digest`, `CHUNKER_VERSION`, model embedding) trùng release hiện hành thì trả
   `no_change`; nếu Qdrant mất point thì ghi lại từ vector của bundle. `bundle_digest` băm nội dung
   tri thức và `chunking`, không băm generator hay file embedding.
4. Trùng một release `ready` chưa retire thì dùng lại (`reused`); trùng release `building` thì chạy
   tiếp release đó.
5. Còn lại: `stage_release` (một transaction, idempotent) ghi danh tính, chunk version và release
   `building`.
6. `IndexWriter` xử lý từng lô (`corpus.embed_batch_size` 32, `corpus.embed_max_concurrent` 1):
   vector lấy từ bundle nếu model và số chiều khớp, thiếu thì gọi embedder; ghi Qdrant ngay. Chạy lại
   sau lỗi bỏ qua point đã có.
7. Số point mang `release_id` bằng số `release_chunks` thì `ready` và ghi `stats`; lệch thì release
   ở lại `building` và lệnh báo lỗi.
8. `--publish`: một transaction đặt `current_release_id` và `published_at`.

| Lệnh `pharma-agent corpus` | Việc |
| --- | --- |
| `import <bundle> --collection <key> [--publish]` | Import bundle thành release |
| `releases [--collection]` | Liệt kê release, trạng thái, số chunk, release hiện hành |
| `publish <release_id>` | Trỏ release hiện hành tới một release `ready` |
| `rollback --collection` | Về release có `published_at` liền trước |
| `gc --collection [--keep N]` | Retire release cũ (mặc định giữ `corpus.gc_keep = 2`), cập nhật `release_ids` trên point, xoá point không còn release sống, xoá chunk version không release nào dùng (trừ chunk bị FK chặn), rồi section và document mồ côi |
| `reindex --collection` | Dựng lại point cho release chưa retire từ Postgres; embed lại toàn bộ qua embedder hiện tại (tốn tiền API). Khi còn bundle, `import` lại rẻ hơn vì dùng vector của bundle |
| `purge-deleted` | Dọn collection đã xoá mềm (cũng chạy trong job bảo trì hằng ngày) |

### 3.5 Qdrant và đọc corpus lúc retrieval

- Một collection vật lý cho mỗi model embedding, `chunks_<model_slug>`: dense `dense_vector`
  (cosine, số chiều theo model) và sparse `bm25_sparse_vector` (modifier IDF, Qdrant server tự suy
  luận BM25 từ `models.Document(embedding_text)`). Metadata collection ghi `{embedding_model, dims}`.
- Alias `chunks_current` (setting `retrieval.qdrant_collection`) được tạo khi chưa có và không tự
  đổi. Server E2E và stack đánh giá dùng alias riêng.
- Point id là `chunk_version_id`. Payload chỉ có `collection_id` (payload index keyword `is_tenant=true`), `release_ids[]`,
  `document_id` (keyword index); không chứa text. HNSW để cấu hình mặc định. `release_ids` luôn được tính lại từ Postgres rồi ghi bằng
  `SetPayload`, không append trong Qdrant.
- Dense vector có thể để trên đĩa (`on_disk_vectors`) cho gói cloud ít RAM.
- Truy vấn: `QdrantHybridRetriever` đọc release hiện hành của các collection trong phạm vi từ
  Postgres ở mỗi lần search (không cache, nên publish và rollback có hiệu lực ngay), lọc theo từng
  cặp `collection_id` và `release_id`, lấy id và điểm (`hybrid` RRF, `dense`, `bm25`), rồi
  `PostgresCorpusReader.load_chunks` nạp text, header, trang, thuật ngữ trong một query.
- Phạm vi: chat qua API tìm trong các collection người dùng được thấy (`PostgresScopeResolver`);
  CLI và harness đánh giá dùng `retrieval.collections` (mặc định `["formulary"]`).
- `/health` và `pharma-agent check` có kiểm `corpus`: collection Qdrant tồn tại, metadata khớp
  model và số chiều đang cấu hình, mọi collection trong phạm vi có release hiện hành. Sai thì
  `degraded` với `CORPUS_NOT_READY`.
- Ràng buộc vận hành: corpus phải được import bằng đúng model embedding mà backend dùng. Local mặc
  định dùng Qwen3-Embedding-4B (2560 chiều), production dùng Qwen3-Embedding-8B (4096 chiều) qua
  OpenRouter, nên corpus import ở môi trường này không dùng được cho môi trường kia.

Vòng agent (số vòng search, gói evidence, `top_n`, citation trả cho client) thuộc spec
`backend-agent-api`.

### 3.6 Corpus người dùng soạn

- Tài liệu Markdown, glossary và tên gọi colloquial do người dùng soạn nằm trong
  `source_documents`, `glossary_entries`, `colloquial_mappings` (`domain/corpus/source.py`).
- Xuất bản (`PublishService`) tạo `ingest_jobs`; job dựng `KnowledgeBundle` bằng
  `domain/corpus/authoring.py` (tách section theo heading, key tài liệu có tiền tố key collection)
  rồi gọi đúng `ImportKnowledgeBundle` với `--publish`. Bundle soạn trong app không kèm vector, nên
  mọi chunk được embed qua embedder đang cấu hình.
- Job idempotent: chạy lại sau lỗi tiếp tục cùng release. Local chạy trong tiến trình sau khi trả
  lời; trên Vercel chạy ngay trong request (giới hạn 300 giây).

Chủ sở hữu, quyền xem, quota và giao diện quản lý collection thuộc spec `product-accounts-orgs`.

### 3.7 Reranker trong backend

- `RerankSettings.protocol ∈ {native_rerank, none}`. `NativeReranker` gửi một request
  `/v1/rerank` cho mỗi vòng search, chứa tối đa `max_candidates` ứng viên (mặc định 40, lấy xen kẽ
  giữa các query theo hạng RRF) và giữ `top_n = 5`. Endpoint có thể là llama.cpp, OpenRouter, TEI
  hay vLLM.
- Mặc định trong mã là server local (`qwen3-reranker:4b-q8_0` ở `localhost:11435`). `.env.example`
  của backend dùng OpenRouter `qwen/qwen3-reranker-8b`, bản Qwen3 reranker duy nhất OpenRouter phục
  vụ.
- Compose local đặt `MAX_CONCURRENT = 1`, `MAX_CANDIDATES = 15` và timeout bằng ít nhất 2 lần p95 CPU
  đo được.

## 4. Thiết kế hiện hành: pharma-lab

### 4.1 Nguồn và build

- Dược thư: `data/sources/duoc-thu-quoc-gia-viet-nam.pdf`.
- Tờ hướng dẫn: `pharma-lab source crawl` đọc sitemap (URL lấy từ manifest; lần đầu cần
  `--sitemap-url`), giữ URL đúng dạng `<nhóm>/<slug>` thuộc danh mục thuốc, ghi
  `leaflets/urls/`, `leaflets/html/<nhóm>/<slug>.html` và `leaflets/manifest.json` (schema
  `leaflet-source-v1`: sitemap URL, ngày crawl, sha256 danh sách URL, path, size, sha256 và URL nguồn
  của từng file).
- `pharma-lab build` kiểm sha256 từng file HTML theo manifest rồi đọc trực tiếp; trích PDF, làm sạch,
  tách section, ghép bảng Docling đã curate, tích hợp tờ hướng dẫn. Kết quả là `corpus/rag-final/`
  theo contract `rag-final-v3`: chỉ `sections.jsonl`, `blocks.jsonl`, `validation_report.json` và
  `manifest.json` (build id, digest nguồn, digest dữ liệu curate). Build chạy trong
  `work/build/in-progress/`, publish nguyên tử; build lỗi giữ ở `work/build/failed/latest/`.
- `pharma-lab bundle export` ánh xạ section và block sang bundle, chép glossary và colloquial
  mapping, ghi vào thư mục tạm, validate bằng `read_bundle` rồi mới thay thư mục đích.
- `pharma-lab bundle embed --backend kaggle|local --model <m>` chạy `chunk_document` để lấy các cặp
  (`sha256(embedding_text)`, `embedding_text`) duy nhất, dùng cache `cache/text_embeddings/<model>.jsonl`,
  embed phần thiếu, rồi ghi `embeddings/<model_slug>.jsonl`. Bundle `formulary` hiện có vector của
  5 model Q8_0: `embeddinggemma:300m`, `bge-m3:567m`, `qwen3-embedding:{0.6b,4b,8b}`. Cơ chế chạy
  kernel và quota thuộc spec `kaggle-runs`.
- `pharma-lab bundle rechunk` sinh bản sao dưới collection khác với chunking khác:
  `formulary-sections` (`target_chars = 1`, mỗi mục một chunk, thí nghiệm D7) và `formulary-plain`
  (`enrichment = false`, thí nghiệm D2).

### 4.2 Tên trung tính cho tờ hướng dẫn

Mọi định danh, prompt, code, test và tài liệu gọi nguồn này là `leaflet` hoặc "tờ hướng dẫn sử
dụng". Test chính sách repo (`pharma-lab/tests/test_repository_data_policy.py`,
`backend/tests/domain/test_prompts.py`) chặn tên website nguồn trong `backend/src`, `backend/skills`,
`pharma-lab/src`, `frontend/app` và trong prompt.

### 4.3 Bố cục `pharma-lab/data/`

```text
data/
├── sources/     PDF Dược thư, leaflets/ (manifest.json, urls/, html/), curation/,
│                colloquial_mappings.json, term_glossary.json, vietnamese_valid_syllables.json
├── corpus/      rag-final/, formulary/, formulary-plain/, formulary-sections/
├── evaluation/  gold/, runs/<run>/ (run.json, candidates/, rerank/<model>/, reports/), e2e/, calibration/
├── cache/       text_embeddings/, query_embeddings/, rerank_scores/ (<model>.jsonl),
│                kaggle_profiles/<workload>/<model>.json, local_profiles/<workload>/<model>.json
└── work/        scratch: build, locks, bundle-embed, archive staging, logs/rerank/<model>.log
```

- Tên file và thư mục không chứa hash; digest và identity nằm trong `manifest.json` hoặc trong từng
  bản ghi cache. `<model>` là slug của catalog, ví dụ `qwen3_embedding_4b_q8_0`.
- Mỗi run đánh giá là một thư mục duy nhất; mở lại run với identity khác thì lệnh dừng và nêu trường
  khác nhau, `--force` thay thế nguyên tử. Lock: `work/locks/<đích>.<job|cache>.lock`.
- Cache chỉ nhận bản ghi đã niêm phong (có checksum); không còn nhánh đọc định dạng cũ.
- Git chỉ giữ file nhỏ: nguồn tự duy trì (trừ PDF và HTML), `manifest.json` và
  `validation_report.json` của corpus, `run.json`, `manifest.json`, `report.md` của run. Hook
  `check-added-large-files` chặn commit nhầm.

### 4.4 Archive dữ liệu

- `pharma-lab data push` liệt kê file bị Git bỏ qua dưới `data/` (trừ `work/`), ghi luồng tar nén
  zstd, cắt thành phần tối đa 1,9 GiB, ghi `archive-manifest.json` (commit, sha256 từng file và từng
  phần) và tạo một version mới của dataset Kaggle private. Push từ chối chạy khi file có trong
  archive hiện tại bị thiếu ở máy, trừ khi có `--allow-removal`; lần push đầu cần chủ dự án xác nhận.
- `pharma-lab data pull [--dataset SLUG] [--version N]` tải, kiểm sha256 từng phần, giải nén, kiểm
  sha256 từng file; file khác checksum thì dừng trừ khi có `--force`.
- Mỗi dòng phiên bản chính của mã có một dataset riêng: `vipharmind-data-v2` cho v2. Các dataset của
  dòng v1 (bài nộp và camera-ready) đã đóng băng và `data push` từ chối ghi vào. Bảng version và tag
  nằm trong `pharma-lab/data/README.md`.

### 4.5 Phục vụ reranker

- Catalog (`runtime/catalog.py`) chỉ có reranker `native_rerank`: `qwen3-reranker:{0.6b,4b,8b}-q8_0`
  và `bge-reranker-v2-m3:q8_0`. Mọi model tự host là bản Q8_0 đã công bố, ghim theo commit Hugging
  Face và sha256.
- Ba file Qwen3 là bản `-vimed`: template `rerank` trong GGUF đổi đúng một dòng instruction thành
  `Given a Vietnamese medical retrieval query, retrieve relevant passages that answer the query`,
  tạo bằng `gguf-new-metadata` (gói `gguf` 0.19.0, chạy tạm qua `uv run --no-project --with`). Lệnh
  và sha256 nằm trong `pharma-lab/docs/guides/evaluation.md`.
- Mọi server reranker (Kaggle và compose) chạy
  `--reranking --kv-unified -np <slots> -c <ub × (slots + 1)> -b <ub> -ub <ub>` với `-ub` tối thiểu
  4096:
  - mỗi tài liệu phải nằm trọn một ubatch (prompt dài nhất của corpus khoảng 2.074 token ở chunker
    cũ, chunk hiện tại tới khoảng 3.100 token);
  - slot giữ KV của prompt trước cho tới khi tài liệu kế của nó vào batch, nên `-c` phải chừa một
    ubatch cho mỗi slot cộng một ubatch, không thì server báo `Context size has been exceeded`;
  - prompt dài hơn `-ub` là lỗi dữ liệu: server trả HTTP 500 `input is too large`, client đánh dấu
    không retry để worker dừng có thông báo thay vì restart server.
- Một `RuntimeCandidate` reranker là một mức server đầy đủ (`-np`, `-ub`, số tài liệu mỗi request,
  số request đồng thời, số luồng CPU). Các mức Kaggle T4 chia theo cỡ model (0.6b, 4b, 8b); mức CPU
  local là `(4, 4096, 1)`, 15 tài liệu mỗi request.
- Benchmark đầu-cuối chạy từng mức trên tải lấy phân tầng theo độ dài, ghi cặp/giây, p50, p95, trạng
  thái, lỗi. Mức đầu tiên hợp lệ là mốc; mức sau xếp hạng ứng viên khác mốc thì `invalid`
  (`rank_mismatch`). Không so điểm tuyệt đối vì cách llama.cpp gom batch làm điểm lệch vài phần
  trăm. Kaggle chọn cặp/giây cao nhất, CPU chọn p95 thấp nhất. Profile lưu ở
  `cache/kaggle_profiles/` và `cache/local_profiles/`.
- Identity tái dùng của job rerank (`reuse_sha256`) bỏ `runtime_profile`, nên đổi cấu hình runtime
  không làm mất checkpoint hay điểm đã chấm. Cache điểm khoá theo `model_sha256` và
  `request_contract_sha256`.
- `pharma-lab rerank --backend local` gửi một request cho mỗi câu hỏi qua service `llama-reranker`;
  `--benchmark` dựng lại service với biến `LLAMA_ARG_*` của từng mức và in cấu hình được chọn.
- `compose.local-models.yaml` (image `llama.cpp:server-b10920`) mặc định `-np 4`, `-ub 4096`,
  `-c 20480`, 12 luồng, đo trên Intel i5-13420H. Phép đo hiện có chạy ở `-ub 2048` (xem mục 6).

### 4.6 Ràng buộc chung

- Python 3.12 (`.python-version`), uv workspace, `ruff.toml` chung, pyrefly strict, pytest coi warning là lỗi,
  import-linter; không thêm `noqa`, `type: ignore` hay tắt rule.
- Không giữ đường tương thích ngược: không cờ, không nhánh legacy, không migration dữ liệu cũ. DB
  production xuất phát trống.
- Lệnh chạy lâu (build, embed, benchmark, chấm Kaggle, push và pull archive) chạy trong tmux; log
  rerank ghi vào `work/logs/rerank/<model>.log`, không nằm trong `/tmp`.

## 5. Ngoài phạm vi

- Tự động chuyển model embedding (tạo collection mới, đổi alias `chunks_current`).
- Trang public và SEO cho corpus.
- Incremental sync hay hàng đợi worker riêng cho import.
- Lượng tử hoá tự làm và đổi engine suy luận (vLLM, TEI) cho phần tự host.
- Phương pháp và số liệu đánh giá retrieval, rerank: spec `evaluation`.
- Phiên Kaggle, chọn tài khoản theo quota, checkpoint qua phiên: spec `kaggle-runs`.

## 6. Vấn đề còn mở

- Mặc định reranker CPU trong `compose.local-models.yaml` lấy từ phép đo ở `-ub 2048` (p95 448,7 giây
  cho request 15 tài liệu), mức này từ chối prompt dài nhất. Cần đo lại ở `-ub 4096` với file Q8_0
  `-vimed` hiện hành. Việc này nằm trong plan `2026-11-15-rerank-cpu-defaults.md`.
- `pharma-lab/README.md` còn ghi `bundle embed` dùng `chunk_section`; tên đúng là `chunk_document`
  (cùng plan trên).

## 7. Lịch sử quyết định

Bản gốc đọc bằng `git -C <repo> show <sha>:<path>`. Plan triển khai của các quyết định dưới đây
đều đã chạy xong và bị bỏ; kết quả nằm trong mã.

| Ngày | Quyết định | Thay cho | Lý do | Nguồn |
| --- | --- | --- | --- | --- |
| 2026-09-13 | Postgres schema `corpus` là nguồn chính, Qdrant là index dẫn xuất; chunk version bất biến với id băm | Corpus chỉ nằm trong payload Qdrant; `chunk_id = "{section_id}:chunk-NNN"` theo vị trí; quy tắc cũ cấm corpus vào Postgres | Id theo vị trí trỏ sang nội dung khác mà không báo khi đổi kích thước chunk hay sửa đoạn trước; Qdrant không có versioning dữ liệu trong collection. Tinh thần tách trạng thái app khỏi corpus giữ bằng schema riêng | `f9fc933:backend/docs/superpowers/specs/2026-09-13-corpus-platform-design.md` §1, §14 |
| 2026-09-13 | Backend sở hữu corpus lúc chạy; pipeline offline bàn giao bằng knowledge bundle và không ghi DB | Package `corpus-store` dùng chung; pipeline tự ghi SQL; pipeline sở hữu schema | Phần runtime vào backend, phần tạo dữ liệu tách riêng; backend không kéo torch, docling | như trên §2, §14 |
| 2026-09-13 | Bàn giao tri thức có cấu trúc (document, section, block), một chunker trong backend | Bàn giao chunk hoàn chỉnh từ pipeline | Một chunker cho cả dữ liệu gốc và dữ liệu người dùng | như trên §14 |
| 2026-09-13 | Một collection Qdrant mỗi model, phân vùng bằng payload `collection_id`, `release_ids` | Một collection mỗi release với alias | Khuyến nghị multitenancy của Qdrant; publish và rollback chỉ đổi con trỏ trong Postgres | như trên §8.3, §14 |
| 2026-09-13 | Citation lưu tham chiếu chunk version (FK `RESTRICT`) | Lưu bản sao `cited_text` | Chunk version bất biến nên không mất nội dung | như trên §14 |
| 2026-09-13 | Đổi tên `corpus-pipeline` thành `seed-pipeline`; evaluation gọi `RetrievalService` của backend | Retriever riêng trong pipeline | Đo đúng retrieval chạy thật | `f9fc933:backend/docs/superpowers/plans/2026-09-13-seed-pipeline.md`; plan domain, store-import, retrieval: `f9fc933:backend/docs/superpowers/plans/2026-09-13-corpus-domain.md`, `875eab9:backend/docs/superpowers/plans/2026-09-13-corpus-store-import.md`, `875eab9:backend/docs/superpowers/plans/2026-09-13-corpus-retrieval.md` |
| 2026-09-13 | Chuyển đổi bằng parity 100% giữa `chunk_section` và `chunks.jsonl` cũ (đạt 0 lệch trên 24.955 chunk), rồi xoá code parity | Chấp nhận lệch | Không đổi chất lượng khi chuyển nền tảng | spec 09-13 §7.3, §11; commit `a492358` xoá parity |
| 2026-09-14 | Bố cục 5 thư mục `sources/corpus/evaluation/cache/work`, tên không hash, một cây cho mỗi run, bỏ code tương thích ngược | `data/heavy/` 18 GB lẫn dữ liệu hai pipeline, run tách hai cây, tên sinh từ hash | Đọc được, dựng lại được, không nhánh legacy | `875eab9:seed-pipeline/docs/superpowers/specs/2026-09-14-seed-data-layout-design.md` §1–§6; plan `875eab9:seed-pipeline/docs/superpowers/plans/2026-09-14-seed-data-layout-code.md` |
| 2026-09-14 | Gọi tờ hướng dẫn là `leaflet`; nguồn gốc chỉ trong manifest nguồn nội bộ; `source.url = null` | Key và URL mang tên website nguồn trong bundle, DB, prompt, gold | Production không được lộ nguồn | spec 09-14 §2, §5, §7.1 |
| 2026-09-14 | Crawl thành cây HTML có manifest sha256 | Snapshot `tar.zst` có hash trong tên | Build kiểm từng file, không giải nén | spec 09-14 §6.4 |
| 2026-09-14 | `corpus gc` xoá cả section và document mồ côi | gc chỉ xoá chunk và revision | Đổi key để lại danh tính cũ | spec 09-14 §6.6; commit `69e534c` |
| 2026-09-14 | Archive Kaggle private bằng `data push/pull`, chia phần 1,9 GiB, kiểm sha256 | Dữ liệu chỉ ở máy | Khôi phục được trên bản clone mới; giới hạn khoảng 2 GB mỗi file khi upload qua API | spec 09-14 §9; plan `f9fc933:pharma-lab/docs/superpowers/plans/2026-09-14-seed-data-archive.md` |
| 2026-09-14 | Chuyển dữ liệu một lần bằng script không commit; dựng lại mọi run bằng CLI mới, ngưỡng Hit@10 không giảm quá 1 điểm, MRR không giảm quá 0,01 | Giữ dữ liệu cũ song song | Chứng minh số liệu trước khi xoá legacy | `f9fc933:pharma-lab/docs/superpowers/plans/2026-09-14-seed-data-migration.md` |
| 2026-09-15 | Bỏ hẳn `completion_logprobs`, chỉ còn `native_rerank` | Chấm yes/no bằng logprobs | GGUF Qwen3-Reranker-8B là bản classifier, llama.cpp lấy nhầm lớp đầu ra nên MRR 0,4797; `/v1/rerank` tính đúng softmax yes/no qua `cls.output.weight` | `f9fc933:pharma-lab/docs/superpowers/specs/2026-09-15-native-rerank-optimisation-design.md` §1, §4.1 |
| 2026-09-15 | Server reranker gom khối với `--kv-unified`, `-ub ≥ 4096`, `-c = ub × (slots + 1)`; chọn mức bằng benchmark đầu-cuối có kiểm thứ hạng | Quét chỉ số request đồng thời, một tài liệu mỗi request, `-ub 2048`, `UBATCH 512` trong compose | Rank pooling không dùng lại cache prompt; GPU chỉ chạy khoảng 30% ở mức ít slot; một prompt 2.074 token làm hỏng cả job ở `-ub 2048` | spec 09-15 §4.2, §4.3; plan `f9fc933:pharma-lab/docs/superpowers/plans/2026-09-15-native-rerank-serving.md` |
| 2026-09-15 | `reuse_sha256` của job rerank bỏ `runtime_profile` | Đổi cấu hình là mất checkpoint | Điểm không phụ thuộc cấu hình runtime | spec 09-15 §4.4 |
| 2026-09-16 | Qwen3 reranker dùng instruction tiếng Việt y tế (`-vimed`) | Template gốc (web search) | Bootstrap theo cặp trên 1.000 câu, quy tắc chốt trước: hiệu MRR@30 0,0445, KTC 95% [0,0306; 0,0585] | `f9fc933:pharma-lab/docs/superpowers/plans/2026-09-15-rerank-instruction-rollout.md`; commit `7c9260f`; `pharma-lab/docs/guides/evaluation.md` |
| 2026-09-16 | Đổi tên `seed-pipeline` thành `pharma-lab` | `seed-pipeline` | Project đã chứa cả phòng thí nghiệm đánh giá, không chỉ build dữ liệu seed; dataset Kaggle giữ tên cũ để khỏi upload lại | commit `1541f79` |
| 2026-10-10 | Bỏ bảng và cột không ai đọc: `glossary_entries`, `colloquial_mappings` theo release, `documents.kind/source_url/attributes`, `sections.context_path/ordinal/retrieval_mode` (migration 0012); bỏ audit retrieval (0011) | Ghi đủ theo spec 09-13 §6.2 | Kết quả enrichment đã nằm trên chunk version; giá trị gốc còn trong bundle | commit `4c4c725`, `e7efa2c` |
| 2026-10-10 | Vector chỉ ở Qdrant và bundle; bỏ `corpus.embedding_cache` và `chunk_versions.embedding_text` (migration 0016); embed từng lô ngay trước khi ghi Qdrant | Cache embedding trong Postgres (khoảng 256 MB) để `reindex` không phải embed lại | Commit ghi: vector chỉ cần ở Qdrant, embedding text dựng lại từ các cột. Đổi lại, `reindex` phải embed lại toàn bộ | commit `afd4b10` |
| 2026-10-10 | Collection có chủ (user, tổ chức, hệ thống), xoá mềm; nội dung soạn trong app và job xuất bản đi qua `ImportKnowledgeBundle` (0018–0020) | Chỉ có corpus hệ thống; schema để sẵn `owner_user_id` | Corpus cá nhân dùng đúng đường ingest của CLI | commit `88f0c17`, `17f4f6b`, `aa70947`; chi tiết ở spec `product-accounts-orgs` |
| 2026-10-15 | Chunk là đơn vị đọc: `chunk_document` gộp mục tới `target_chars` 4.200, `max_chars` 5.600, `chunker-v2`; bỏ hydrate, `section_revisions`, `hydrate_strategy`, `RetrievalMode.INDEX_ONLY` (migration 0021); rag-final bỏ `chunks.jsonl` | `chunk_section` mỗi mục một chunk (`chunker-v1`, 3.000 ký tự), hydrate `full_section`/`chunk_window`/`search_only` | Mỗi mục một chunk cho 42.567 chunk trung bình 372 token; 91% mục chỉ có một chunk nên hydrate tốn truy vấn mà không thêm thông tin. Target 3.200 cho trung bình 781 token, 4.200 cho khoảng 1.000 | `v2.0.0:docs/superpowers/specs/2026-10-14-paper-v2-design.md` §3.0c; plan `414e317:docs/superpowers/plans/2026-10-15-chunk-reading-unit.md`; commit `1b6f515` |
| 2026-10-15 | Mọi model tự host là Q8_0 đã công bố, ghim theo commit; file F16 xoá | Giữ F16 ở mọi nơi (spec 09-15) | Sinh token trên T4 bị giới hạn băng thông bộ nhớ; Q8_0 nửa dung lượng, chất lượng gần F16, mỗi model vừa một T4 | paper-v2 spec (commit `03a1d62`, `04b7402`); commit `1fdfab1` |
| 2026-10-16 | Manifest bundle khai báo `chunking`; `bundle rechunk` sinh biến thể D2, D7 | Chunking cố định trong mã | Thí nghiệm ablation không cần sửa chunker | commit `6143ea4` |
| 2026-10-16 | Backend mặc định gọi OpenRouter cho embedding và reranker (8B) | Server llama.cpp local hoặc DeepInfra | Một key cho mọi model; production trên Vercel | commit `3eb0eb4`; `backend/.env.example` |
| 2026-10-26 | Mỗi collection Qdrant của stack đánh giá chỉ chứa corpus `formulary`; biến thể chạy trên stack riêng | Chung collection với `formulary_plain`, `formulary_sections` | Point thừa làm HNSW có bộ lọc release mất recall (dense 4B Hit@20 90,0% so với 97,2% khi tìm chính xác) và làm lệch IDF của BM25 | paper-v2 spec §3.4 (sự cố đo 2026-10-26) |

## 8. Liên kết

- `2026-11-15-backend-agent-api-design.md`: vòng agent, evidence, citation API.
- `2026-11-15-product-accounts-orgs-design.md`: chủ sở hữu, quyền và quota của collection, xuất bản
  trong app, ra mắt production (nạp corpus lên Neon và Qdrant).
- `2026-11-15-architecture-rules-design.md`: quy tắc tầng và import-linter.
- `2026-11-15-kaggle-runs-design.md`: embed bundle và chấm rerank trên Kaggle, quota, checkpoint.
- `2026-11-15-evaluation-design.md`: benchmark, gold, run retrieval và rerank, số liệu.
- `2026-11-15-soict-paper-design.md`: thí nghiệm D2, D7 và số liệu trong bài.
- Plan còn mở: `docs/superpowers/plans/2026-11-15-rerank-cpu-defaults.md`.
