# Đánh giá retrieval

Guide này dựng lại các số liệu retrieval của luận văn từ dữ liệu trong archive. Lệnh `uv run pharma-lab` chạy trong `pharma-lab/`, lệnh `uv run pharma-agent` chạy trong `backend/`, lệnh `docker compose` chạy ở thư mục gốc repo.

## 1. Dữ liệu

```bash
uv run pharma-lab data pull --kaggle-account acc1
```

Lệnh tải bundle `data/corpus/formulary` (embedding của 5 model), bộ gold `data/evaluation/gold`, candidates và artifact rerank của các run, cache vector query và điểm rerank, rồi kiểm sha256 từng file. `run.json`, manifest và `report.md` của các run đã có trong Git.

Metrics đọc thêm file nhãn `data/evaluation/gold/section_retrieval_eval.judgments.jsonl` (kèm `section_retrieval_eval.judgments.manifest.json` ghi sha256 của bộ gold và phiên bản luật). Với câu hỏi nhóm `formulary` và `multi_intent`, gold chỉ ghi section Dược thư; file nhãn chấp nhận thêm chunk của tờ hướng dẫn biệt dược có đúng các hoạt chất của chuyên luận đó và nằm trong mục trả lời cùng ý hỏi (chỉ định, liều dùng, chống chỉ định, tác dụng phụ, quá liều, thận trọng, dược lý, tương tác, thai kỳ và cho con bú). Hoạt chất đọc từ mục "Thành phần" của trang; thuốc phối hợp chỉ khớp chuyên luận phối hợp cùng thành phần. Mục của chunk lấy theo heading của trang, kể cả dòng tiêu đề mất dấu `#` như "- Thận trọng khi sử dụng". Đổi luật chỉ cần dựng lại file nhãn rồi chạy lại metrics; candidates, cache embedding và điểm rerank giữ nguyên:

```bash
uv run pharma-lab evaluation judgments
uv run pharma-lab metrics --run hybrid-qwen4b-p50-k30-rrf2 --top-k 30 --force
```

Report ghi `judgments_sha256` trong identity, và `pharma-lab metrics compare` chỉ so hai report dùng cùng file nhãn.

## 2. Môi trường riêng cho đánh giá

```bash
POSTGRES_PORT=5434 QDRANT_HTTP_PORT=6335 docker compose -p vipharmind-eval up -d --wait postgres qdrant
export PHARMA_POSTGRES__DSN=postgresql+psycopg://vipharmind:vipharmind@localhost:5434/vipharmind
export PHARMA_QDRANT__URL=http://localhost:6335
```

Stack `vipharmind-eval` tách khỏi stack của app (cổng 5433 và 6333). Không cần llama.cpp: vector chunk có sẵn trong bundle, vector query có sẵn trong cache, `pharma-lab retrieve` tắt rerank. Xong việc: `docker compose -p vipharmind-eval down -v`.

## 3. Chạy một model

Mỗi model đọc và ghi alias Qdrant riêng `eval_<model_slug>` qua `PHARMA_RETRIEVAL__QDRANT_COLLECTION`. `pharma-agent corpus import` tạo alias khi chưa có nhưng không chuyển một alias đã có sang collection của model khác, nên dùng chung một alias cho nhiều model sẽ truy vấn nhầm vector. Import và publish model trước khi retrieve, vì `pharma-lab retrieve` đọc release đang publish.

```bash
export PHARMA_RETRIEVAL__EMBEDDING__MODEL=qwen3-embedding:4b-q8_0
export PHARMA_RETRIEVAL__EMBEDDING__DIMENSION=2560
export PHARMA_RETRIEVAL__QDRANT_COLLECTION=eval_qwen3_embedding_4b_q8_0
```

Trong `backend/`:

```bash
uv run pharma-agent corpus import ../pharma-lab/data/corpus/formulary --collection formulary --publish
```

Trong `pharma-lab/`:

```bash
uv run pharma-lab retrieve --run dense-qwen4b-k30 --retriever dense --candidate-k 30 --force
uv run pharma-lab retrieve --run bm25-qwen4b-k30 --retriever bm25 --candidate-k 30 --force
uv run pharma-lab retrieve --run hybrid-qwen4b-p50-k30-rrf60 --retriever hybrid --prefetch-k 50 --candidate-k 30 --rrf-k 60 --force
uv run pharma-lab metrics --run hybrid-qwen4b-p50-k30-rrf60 --top-k 30 --force
```

`--force` thay run tải từ archive, vì stack mới có release id khác. Mỗi lần retrieve 10.000 query mất khoảng 10–20 phút.

| Model | Chiều vector | `PHARMA_RETRIEVAL__QDRANT_COLLECTION` | Run |
| --- | ---: | --- | --- |
| `embeddinggemma:300m-q8_0` | 768 | `eval_embeddinggemma_300m_q8_0` | `dense-gemma300m-k30` |
| `bge-m3:567m-q8_0` | 1024 | `eval_bge_m3_567m_q8_0` | `dense-bge-m3-k30` |
| `qwen3-embedding:0.6b-q8_0` | 1024 | `eval_qwen3_embedding_0_6b_q8_0` | `dense-qwen06b-k30` |
| `qwen3-embedding:8b-q8_0` | 4096 | `eval_qwen3_embedding_8b_q8_0` | `dense-qwen8b-k30` |
| `qwen3-embedding:4b-q8_0` | 2560 | `eval_qwen3_embedding_4b_q8_0` | `dense-qwen4b-k30`, `bm25-qwen4b-k30`, `hybrid-qwen4b-p50-k30-rrf2`, `hybrid-qwen4b-p50-k30-rrf60` |

## 4. Rerank

```bash
uv run pharma-lab rerank --run hybrid-qwen4b-p50-k30-rrf2 --model qwen3-reranker:4b-q8_0 --dry-run
uv run pharma-lab rerank --run hybrid-qwen4b-p50-k30-rrf2 --model qwen3-reranker:4b-q8_0
uv run pharma-lab metrics --run hybrid-qwen4b-p50-k30-rrf2 --model qwen3-reranker:4b-q8_0 --top-k 30
```

`--dry-run` in `missing_pairs=N`, số cặp query–chunk chưa có điểm trong `data/cache/rerank_scores/`; rerank chỉ chạy model cho các cặp đó.

Mọi reranker được gọi qua `/v1/rerank`.

Cấu hình `llama-reranker` cho backend trên CPU được chọn bằng benchmark đầu-cuối trên máy production (chạy trong tmux: mỗi mức nạp lại model 4B trên CPU):

```bash
uv run pharma-lab rerank --run hybrid-qwen4b-p50-k30-rrf2 --backend local --benchmark --model qwen3-reranker:4b-q8_0
```

Lệnh lưu `data/cache/local_profiles/rerank/<model>.json` và in các biến `LLAMA_RERANKER_*` cho `.env` ở gốc repo. Trên Kaggle, benchmark chạy tự động trước lần chấm đầu tiên khi chưa có profile khớp (xem [CLI reference](cli-reference.md)).

Qdrant tìm dense bằng HNSW (gần đúng), nên retrieve lại trên index dựng mới có thể chọn khác vài chunk có điểm sát nhau ở cuối top 30. Lần dựng lại tháng 9/2026 lệch 4.678 trên 300.000 cặp, gần hết ở hạng 21–30. Khi đó `N` lớn hơn 0 và cần chạy reranker (CPU hoặc Kaggle) cho các cặp còn thiếu.

### D7: đơn vị đọc theo từng mục

Ablation D7 (spec v2 §4.D) so chunk gộp mục tới khoảng 1.024 token với chunk theo từng mục, cùng
Qwen3-Embedding-4B, cùng hybrid rrf2 và Qwen3-Reranker-4B, cùng benchmark. Manifest của bundle khai
báo cách chia (`chunking.target_chars`, `chunking.max_chars`); `target_chars=1` cho mỗi mục một
chunk, mục dài hơn `max_chars` vẫn được cắt như thường. `bundle rechunk` chép bundle sang collection
khác, không kèm vector; `bundle embed` chỉ embed text chunk chưa có trong cache
`data/cache/text_embeddings/`.

```bash
cd pharma-lab
uv run pharma-lab bundle rechunk --bundle data/corpus/formulary --out data/corpus/formulary-sections --collection formulary_sections --title "Dược thư và tờ hướng dẫn, một chunk mỗi mục" --target-chars 1
uv run pharma-lab bundle embed --bundle data/corpus/formulary-sections --backend kaggle --model qwen3-embedding:4b-q8_0 --kaggle-account acc3

cd ../backend
export PHARMA_POSTGRES__DSN=postgresql+psycopg://vipharmind:vipharmind@localhost:5434/vipharmind
export PHARMA_QDRANT__URL=http://localhost:6335
export PHARMA_RETRIEVAL__EMBEDDING__MODEL=qwen3-embedding:4b-q8_0
export PHARMA_RETRIEVAL__EMBEDDING__DIMENSION=2560
export PHARMA_RETRIEVAL__QDRANT_COLLECTION=eval_qwen3_embedding_4b_q8_0_sections
uv run pharma-agent corpus import ../pharma-lab/data/corpus/formulary-sections --collection formulary_sections --publish

cd ../pharma-lab
uv run pharma-lab retrieve --run hybrid-qwen4b-v2-sections-p50-k20-rrf2 --collection formulary_sections --retriever hybrid --prefetch-k 50 --candidate-k 20 --rrf-k 2
uv run pharma-lab rerank --run hybrid-qwen4b-v2-sections-p50-k20-rrf2 --backend kaggle --model qwen3-reranker:4b-q8_0 --kaggle-account auto
for r in hybrid-qwen4b-v2-sections-p50-k20-rrf2 hybrid-qwen4b-v2-p50-k20-rrf2; do
  uv run pharma-lab metrics --run "$r" --model qwen3-reranker:4b-q8_0 --top-k 20 --gold-only
done
```

Hai bên D7 chấm bằng `--gold-only`: chỉ chunk chứa mục gold mới tính, không dùng relevance
judgments, vì nhãn chunk được chấp nhận trong judgments thuộc cách chia mặc định. Report nằm ở
`reports/rerank/<model>/top20-gold/` (và `reports/baseline/top20-gold/` khi bỏ `--model`), cạnh report
có judgments.

## 5. File GGUF

Mọi model tự host là bản Q8_0 đã công bố, tải theo commit và kiểm sha256, không tự quantize. Q8_0 giữ chất lượng gần như F16 với nửa dung lượng, và sinh token trên T4 bị giới hạn bởi băng thông bộ nhớ, nên mỗi model vừa một T4 và chạy một bản trên mỗi GPU.

| Model | Repo | Commit | File tải về | sha256 |
| --- | --- | --- | --- | --- |
| `qwen3.5:9b-q8_0` | `unsloth/Qwen3.5-9B-GGUF` | `3885219b6810b007914f3a7950a8d1b469d598a5` | `Qwen3.5-9B-Q8_0.gguf` | `809626574d0cb43d4becfa56169980da2bb448f2299270f7be443cb89d0a6ae4` |
| `qwen3-embedding:0.6b-q8_0` | `Qwen/Qwen3-Embedding-0.6B-GGUF` | `370f27d7550e0def9b39c1f16d3fbaa13aa67728` | `Qwen3-Embedding-0.6B-Q8_0.gguf` | `06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439` |
| `qwen3-embedding:4b-q8_0` | `Qwen/Qwen3-Embedding-4B-GGUF` | `f4602530db1d980e16da9d7d3a70294cf5c190be` | `Qwen3-Embedding-4B-Q8_0.gguf` | `b60ae5ce2dd6a0b77f82cadf21def1f310a3e10cde380ad0081b07a9d416949d` |
| `qwen3-embedding:8b-q8_0` | `Qwen/Qwen3-Embedding-8B-GGUF` | `69d0e58a13e463cd99a9b83e3f5fee7c10265fab` | `Qwen3-Embedding-8B-Q8_0.gguf` | `d20ddc71e8a5c4344f2343481e242233a997dc5eaff442427a945836c97b4deb` |
| `bge-m3:567m-q8_0` | `gpustack/bge-m3-GGUF` | `2d48f1737679ad900d5c26c5aad5410e9c70fdca` | `bge-m3-Q8_0.gguf` | `950f4a8e5e19477a6d3c26d2f162233c20002c601f75e4b002e3239997821167` |
| `embeddinggemma:300m-q8_0` | `ggml-org/embeddinggemma-300M-GGUF` | `0f741b5a6585bd53aeb15cd1372c56f2a0f65e12` | `embeddinggemma-300M-Q8_0.gguf` | `b5ce9d77a3fc4b3b39ccb5643c36777911cc4eb46a66962eadfa3f5f60490d63` |
| `bge-reranker-v2-m3:q8_0` | `gpustack/bge-reranker-v2-m3-GGUF` | `3093af03b1a635e67b084b1d8c03c5f5e020fd05` | `bge-reranker-v2-m3-Q8_0.gguf` | `a43c7c9b11a4c1517e5bf95151960e1621d1b72f7a493364b01e386cf1aaa1d3` |
| `qwen3-reranker:0.6b-q8_0` | `ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF` | `a02f48bb4f057028298c21fa033da2b30d7742d5` | `qwen3-reranker-0.6b-q8_0.gguf` | `22c9979ce4fbcdc5acdc310c6641c32797eff1aa980b8f7a2db8a8ea23429a48` |
| `qwen3-reranker:4b-q8_0` | `Voodisss/Qwen3-Reranker-4B-GGUF-llama_cpp` | `1b452c803342e73ac3644551b727dfd51a09fd5b` | `Qwen3-Reranker-4B.Q8_0.gguf` | `102ac400d68f02877c2fdfecf0732872652298448352b6faf28ec7f8dca8c913` |
| `qwen3-reranker:8b-q8_0` | `sinjab/Qwen3-Reranker-8B-Q8_0-GGUF` | `1a752c69213196777ef126e132a4a679fbb16af3` | `Qwen3-Reranker-8B-Q8_0.gguf` | `b0f8d65d024ad587a9d14ba91f1f0e3fc2ad59e11e46a3b7e00249c5efa11096` |

Tải một file ở thư mục gốc repo bằng `hf` của workspace, kiểm sha256, rồi đặt dưới tên `canonical_filename` của catalog (`runtime/catalog.py`). Ví dụ với embedding 4B:

```bash
uv run hf download Qwen/Qwen3-Embedding-4B-GGUF Qwen3-Embedding-4B-Q8_0.gguf \
  --revision f4602530db1d980e16da9d7d3a70294cf5c190be --local-dir ai-models/downloads
echo "b60ae5ce2dd6a0b77f82cadf21def1f310a3e10cde380ad0081b07a9d416949d  ai-models/downloads/Qwen3-Embedding-4B-Q8_0.gguf" | sha256sum -c -
mv ai-models/downloads/Qwen3-Embedding-4B-Q8_0.gguf ai-models/gguf/qwen3-embedding-4b-q8_0.gguf
```

Lần chạy stage đầu tiên trên Kaggle tự đưa file lên dataset `vector-cache-gguf-<file>`.

### Reranker Qwen3 với instruction tiếng Việt y tế

Qwen3-Reranker đọc instruction từ template `rerank` trong file GGUF. llama.cpp `/v1/rerank` dùng template đó cùng tensor phân loại `cls.output.weight`, và cả ba file Qwen3 tải về đều có hai thứ này. Template gốc dùng `<Instruct>: Given a web search query, retrieve relevant passages that answer the query`. Bản `-vimed` chỉ đổi dòng đó thành `<Instruct>: Given a Vietnamese medical retrieval query, retrieve relevant passages that answer the query`.

Quy tắc quyết định được chốt trước khi đo: bootstrap theo cặp trên tập con 1.000 câu, 10.000 lần lấy mẫu lại, seed 0, cho hiệu MRR@30 (tiếng Việt − gốc). Phép đo trên benchmark trước cho hiệu 0,0445, khoảng tin cậy 95% [0,0306; 0,0585], nên cả ba reranker Qwen3 dùng instruction tiếng Việt. Plan pha D có bước tuỳ chọn đo lại trên benchmark v2.

`gguf` 0.19.0 chỉ chạy tạm qua `uv run --no-project --with`, không phải dependency của project. `gguf-new-metadata --chat-template` thay mọi khoá `tokenizer.chat_template*`, nên bước đầu ghi danh sách JSON gồm template `default` chép từ file gốc và template `rerank` đã đổi instruction, và dừng nếu file không mang template gốc. Với mỗi cỡ (`SIZE` và file tải về: `0.6b` `qwen3-reranker-0.6b-q8_0.gguf`, `4b` `Qwen3-Reranker-4B.Q8_0.gguf`, `8b` `Qwen3-Reranker-8B-Q8_0.gguf`):

```bash
SIZE=0.6b
SOURCE=ai-models/downloads/qwen3-reranker-0.6b-q8_0.gguf
TEMPLATES=pharma-lab/data/work/vimed/qwen3-reranker-${SIZE}-q8_0.chat-templates.json
mkdir -p pharma-lab/data/work/vimed
uv run --no-project --with gguf==0.19.0 python - "$SOURCE" "$TEMPLATES" <<'EOF'
import json
import sys

from gguf import GGUFReader

ORIGINAL = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on "
    'the Query and the Instruct provided. Note that the answer can only be "yes" or '
    '"no".<|im_end|>\n<|im_start|>user\n<Instruct>: Given a web search query, retrieve '
    "relevant passages that answer the query\n<Query>: {query}\n<Document>: {document}"
    "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
)
OLD_LINE = "<Instruct>: Given a web search query, retrieve relevant passages that answer the query\n"
NEW_LINE = "<Instruct>: Given a Vietnamese medical retrieval query, retrieve relevant passages that answer the query\n"

source, output = sys.argv[1], sys.argv[2]
fields = GGUFReader(source).fields
if fields["tokenizer.chat_template.rerank"].contents() != ORIGINAL:
    raise SystemExit(f"STOP: {source} does not carry the original rerank template")
templates = [
    {"name": "default", "template": fields["tokenizer.chat_template"].contents()},
    {"name": "rerank", "template": ORIGINAL.replace(OLD_LINE, NEW_LINE)},
]
with open(output, "w", encoding="utf-8") as handle:
    json.dump(templates, handle, ensure_ascii=False)
print(f"wrote {output}")
EOF
uv run --no-project --with gguf==0.19.0 gguf-new-metadata \
  --chat-template "$(cat "$TEMPLATES")" "$SOURCE" ai-models/gguf/qwen3-reranker-${SIZE}-q8_0-vimed.gguf
sha256sum ai-models/gguf/qwen3-reranker-${SIZE}-q8_0-vimed.gguf
```

Lệnh cho kết quả tất định. So với file tải về, mọi tensor giống từng byte và chỉ khoá `tokenizer.chat_template.rerank` khác.

| File | Kích thước (byte) | sha256 |
| --- | ---: | --- |
| `qwen3-reranker-0.6b-q8_0-vimed.gguf` | 639.153.216 | `ec7dc43df4b778258631125d3366d1b4bc8543d9594fbd02650a0332db95180e` |
| `qwen3-reranker-4b-q8_0-vimed.gguf` | 4.279.678.912 | `424c3a97b813b53760ffce9fe266fc85cc092c215a5adfef543200f7bde5e526` |
| `qwen3-reranker-8b-q8_0-vimed.gguf` | 8.047.134.176 | `79011330370fdf760fd2d0bd87688826396e06843e682f58f51f60fc43969aef` |

## 6. Cách tính chỉ số

Kết quả của bài nằm trong `report.md` của từng run (`data/evaluation/runs/<run>/reports/`).

### Chọn trên dev, báo cáo trên test

Hằng số RRF `k` và instruction của reranker được chọn trên chính benchmark mà bài báo cáo. Lệnh sau chia 10.000 câu thành dev và test (một nửa mỗi `eval_group`, làm tròn xuống cho dev, seed cố định), lặp lại từng lựa chọn chỉ bằng nửa dev rồi báo cáo mọi phương án trên nửa test. Nó chỉ đọc metric từng câu của các run đã có, không chạy model.

```bash
uv run pharma-lab evaluation dev-test --seed 0
```

- `k ∈ {2, 60}`: chọn theo Hit@10 trước rerank của `hybrid-qwen4b-p50-k30-rrf2` và `-rrf60` trên dev; test báo Hit@10, MRR@10, nDCG@10 của cả hai và của rrf2 sau Qwen3-Reranker-4B.
- Instruction: chọn theo MRR@30 của Qwen3-Reranker-0.6B trong run `hybrid-qwen4b-p50-k30-rrf2-sample1000`, chỉ trên các câu của pilot thuộc dev; test báo các câu pilot thuộc test.

Kết quả ghi vào `data/evaluation/dev-test/report.json` và `report.md`.

### Lớp nào giúp ở đâu (slice)

Slice là thuộc tính của câu hỏi và corpus, không phụ thuộc kết quả hệ thống: `rare_term` (câu hỏi có một từ xuất hiện trong tối đa 10 section và có trong section gold, nơi nửa BM25 của hybrid có lợi) và `sibling_products` (tờ hướng dẫn có tờ khác cùng thương hiệu và cùng hoạt chất, nơi reranker quyết định thứ tự). Lệnh sau tính tỉ lệ câu mà một lớp thắng, trong và ngoài slice, từ metric từng câu của các run đã có:

```bash
uv run pharma-lab evaluation slices
```

Kết quả ghi vào `data/evaluation/slices/report.json` và `report.md`.

**Cách tính nDCG@10 và MRR@k.** Gain là nhị phân. Mỗi đơn vị bằng chứng chỉ được tính gain một lần, tại chunk đầu tiên thoả nó:
- câu single hoặc any_acceptable có 1 đơn vị;
- câu multi_required có mỗi section gold là một đơn vị;
- chunk được file nhãn chấp nhận cũng thoả đơn vị tương ứng.

IDCG giả định mọi đơn vị nằm ở các vị trí đầu. Với câu một đáp án, nDCG@10 = 1/log2(hạng + 1) của chunk trúng đầu tiên, như benchmark known-item (BEIR, MTEB). MRR@10 tính 0 cho chunk trúng sau hạng 10; MRR@30 xét toàn bộ 30 ứng viên.

Với câu multi_required, `Recall@k` là tỉ lệ section gold có trong top-k; `Complete-evidence rate@k` là tỉ lệ câu có đủ mọi section.
