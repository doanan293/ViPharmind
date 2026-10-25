# CLI reference

Public entrypoint:

```text
uv run pharma-lab
```

Các command chính:

```text
pharma-lab doctor --backend local|kaggle
pharma-lab source crawl [--sitemap-url URL]
pharma-lab build [--leaflets-dir DIR]
pharma-lab validate
pharma-lab bundle export --output DIR
pharma-lab bundle embed --bundle DIR --backend local|kaggle --model MODEL [--kaggle-account auto|accN[,accM]] [--parallel N] [--drain]
pharma-lab bundle rechunk --bundle DIR --out DIR --collection KEY --title TITLE --target-chars N
pharma-lab evaluation build [--bundle DIR]
pharma-lab evaluation judgments [--evaluation FILE] [--bundle DIR]
pharma-lab embed queries --backend local|kaggle [--kaggle-account auto|accN[,accM]] [--parallel N] [--drain]
pharma-lab retrieve --run NAME [--limit N | --sample N [--sample-seed S]]
pharma-lab rerank --run NAME --backend local|kaggle --model MODEL [--kaggle-account auto|accN[,accM]] [--parallel N] [--drain] [--max-runs N] [--recover-kernel OWNER/SLUG]
pharma-lab rerank --run NAME --backend local --benchmark --model MODEL
pharma-lab metrics --run NAME [--gold-only]
pharma-lab metrics select --config LABEL=RUN[@MODEL] ... --metric M --secondary M [--exclude-group G]
pharma-lab e2e golden sample|resample|multi-hop-candidates|answerable-candidates|multi-turn-candidates|draft|check|build|pharmacist-pack|pharmacist-score
pharma-lab e2e run --run NAME --config CONFIG [--pipeline-option KEY=VALUE ...] [--limit N] [--deadline-seconds S] [--retry-errors]
pharma-lab e2e judge --run NAME --config CONFIG_DIR [--judge-model MODEL] [--judge-reasoning none|low|medium] [--force]
pharma-lab e2e calibration export|refresh|score --run NAME
pharma-lab e2e decision-probe [--chars N] [--bundle DIR]
pharma-lab e2e decision-set build|guard-draft|score
pharma-lab e2e report --run NAME [--latency-run NAME]
pharma-lab e2e compare --run-a NAME --run-b NAME [--config CONFIG_DIR] [--config-b CONFIG_DIR]
pharma-lab e2e run --backend kaggle --run NAME --config CONFIG [--config ...] [--category CATEGORY ...] [--pipeline-option KEY=VALUE ...] [--llm qwen|gemini|opus] [--kaggle-account auto|accN[,accM]] [--parallel N] [--budget-seconds S] [--max-sessions K] [--drain] [--retry-stuck] [--judge] [--latency] [--with-proxy-credentials [--proxy-credential FILE ...] [--proxy-credentials-dir DIR]]
pharma-lab e2e status --run NAME --config CONFIG [--config ...] [--category CATEGORY ...] [--limit N]
pharma-lab kaggle status [--kaggle-account auto|accN[,accM]] [--delete-leftover-credentials]
```

Global `--json` in envelope máy đọc được, `--debug` bật traceback. `uv run pharma-lab COMMAND --help` cho default thực tế.

## Nguồn và build

| Command | Việc |
| --- | --- |
| `pharma-lab source crawl [--leaflets-dir DIR] [--sitemap-url URL] [--workers N] [--force] [--dry-run]` | Đọc sitemap index và các sitemap con, giữ trang thuốc dạng `<nhóm>/<slug>`, ghi `html/<nhóm>/<slug>.html`, `urls/all_urls.txt`, `urls/drug_urls.txt` và `manifest.json`; lần đầu cần `--sitemap-url`, các lần sau đọc từ manifest |
| `pharma-lab build [--leaflets-dir DIR] [--pdf FILE] [--work-root DIR] [--final-dir DIR]` | Kiểm sha256 từng file HTML theo `data/sources/leaflets/manifest.json`, build trong `data/work/build/in-progress/` rồi publish `data/corpus/rag-final/`; build lỗi giữ ở `data/work/build/failed/latest/` |

## Bundle

| Command | Việc |
| --- | --- |
| `pharma-lab bundle export --output DIR [--rag-final-dir DIR] [--glossary FILE] [--mappings FILE] [--force]` | Đọc `rag-final/{sections,blocks,manifest}` và resources, xuất `knowledge-bundle/v1`, validate bằng `read_bundle` trước khi thay `DIR` |
| `pharma-lab bundle embed --bundle DIR --backend local\|kaggle --model MODEL [--cache FILE] [--work-dir DIR] [--kaggle-account accN] [--dry-run] [--force]` | Gom cặp `(embedding_text_sha256, embedding_text)` duy nhất, embed phần thiếu, ghi `embeddings/<model_slug>.jsonl` và manifest; exit 3 nếu Kaggle chưa xong (chạy lại để resume) |
| `pharma-lab bundle rechunk --bundle DIR --out DIR --collection KEY --title TITLE --target-chars N [--max-chars M]` | Chép nội dung bundle sang collection `KEY` với cách chia chunk mới ghi trong manifest (`chunking`), không kèm vector; `--target-chars 1` cho mỗi mục một chunk (ablation D7, `evaluation.md` §4) |

`--model` của `bundle embed` phải trùng `PHARMA_RETRIEVAL__EMBEDDING__MODEL` của backend, ví dụ `qwen3-embedding:4b-q8_0`. Cache nằm ở `data/cache/text_embeddings/<model-slug>.jsonl`; Kaggle dùng dataset input riêng tư `pipeline-input-<hash>` của tài khoản chạy kernel, như mọi stage khác; stage `corpus-embed` contract version 3.

## Run, retriever và model

`--run NAME` là thư mục `data/evaluation/runs/NAME/`: `run.json` (identity và `origin`), `candidates/`, `rerank/<model>/`, `reports/`. Retrieve, rerank và metrics mở lại cùng thư mục; input khác identity thì lệnh dừng và nêu các trường khác nhau, `--force` thay thế cả run.

`pharma-lab retrieve` dựng retrieval stack của backend bằng `build_retrieval_service(settings, embedder=...)`:

- Settings đọc từ `--backend-env-file` (mặc định `../backend/.env`), gồm Postgres, Qdrant, tên và số chiều của model embedding.
- Lệnh ghi đè `retrieval.mode`, `candidate_k`, `prefetch_k`, `rrf_k`, `collections = [--collection]` (mặc định `formulary`), tắt rerank (`protocol = none`) và Langfuse.
- `dense` và `hybrid` dùng vector query có sẵn trong cache của `pharma-lab embed queries` (`--query-embeddings`, mặc định `data/cache/query_embeddings/<model-slug>.jsonl` theo `PHARMA_RETRIEVAL__EMBEDDING__MODEL`). Thiếu vector của query nào thì lệnh dừng trước khi retrieve; evaluation không bao giờ embed query qua endpoint. `bm25` không cần vector query.
- Phải có release đã import và publish; release lấy từ query đầu tiên và mọi hit sau phải cùng release.
- Run identity: evaluation path/sha256, collection Qdrant, `embedding_model`, `query_embeddings_sha256`, `retriever`, K, `limit`, `sample`, `sample_seed`, `release_id`, `chunker_version`.

| Retriever | Query embeddings | Qdrant | Candidate semantics |
| --- | --- | --- | --- |
| `bm25` | Không dùng | BM25 sparse | `candidate-k` là retrieval limit |
| `dense` | Bắt buộc, từ cache | dense | `candidate-k` là retrieval limit |
| `hybrid` | Bắt buộc, từ cache | dense + BM25 sparse, RRF | `prefetch-k` mỗi nhánh, `candidate-k` sau RRF |

```bash
uv run pharma-lab retrieve \
  --run backend-hybrid-qwen4b-v3-p50-k20-rrf2 \
  --retriever hybrid \
  --prefetch-k 50 \
  --candidate-k 30 \
  --rrf-k 2
```

Candidate `chunk_id` là nhãn vị trí `<document_key>:chunk-<ordinal:03d>` của chunk gộp mục, kèm `section_ids` các mục nó chứa, `document_text` là `embedding_text` của chunk (dùng cho rerank).

`--limit N` lấy N dòng đầu của file gold. `--sample N` lấy mẫu phân tầng theo `eval_group`: mỗi nhóm nhận số câu tỉ lệ với cỡ nhóm, làm tròn theo phần dư lớn nhất (phần dư bằng nhau thì nhóm xuất hiện trước trong file được ưu tiên), chọn ngẫu nhiên trong nhóm bằng `--sample-seed` (mặc định 0) và giữ thứ tự của file. Hai tuỳ chọn loại trừ nhau. Với bộ gold 10.000 câu, `--sample 1000` cho 500 `formulary`, 250 `leaflet`, 100 `chunk_risk`, 50 `leaflet_short`, 50 `noisy`, 50 `multi_intent`.

```bash
uv run pharma-lab retrieve --run hybrid-qwen4b-v3-p50-k20-rrf2-sample1000 --retriever hybrid --prefetch-k 50 --candidate-k 20 --rrf-k 2 --sample 1000 --sample-seed 0
```

## Rerank và metrics

`pharma-lab rerank` chỉ đọc candidates của run; với Kaggle, stage chỉ load reranker và chấm candidate pairs. Mỗi reranker có đúng một biến thể dưới `rerank/<model>/` của run. `--dry-run` in `target=` và `missing_pairs=N`, số cặp query–chunk chưa có điểm trong `data/cache/rerank_scores/<model>.jsonl`; khi cache đã đủ, rerank không khởi động model.

Với `--backend kaggle`, job chạy thành nhiều phiên GPU. `--kaggle-account auto` đọc `kaggle quota -v` của mọi profile trước mỗi phiên và chọn tài khoản còn nhiều giờ nhất (bằng nhau thì `accN` nhỏ hơn) mà không bị lệnh khác khoá; `--kaggle-account accN` giữ một tài khoản. Ngân sách phiên = min(`--budget-seconds`, quota còn lại − 0,5 giờ), tối thiểu 1 giờ nên `--budget-seconds` phải ≥ 3600. Lệnh dừng khi đủ cặp (`stop=complete`), hết quota (`stop=quota-exhausted`, exit 3, in bảng quota với `refresh_at`), một shard không thêm gì hai lần (`stop=stuck`), đạt `--max-runs N` (`stop=max-sessions`) hoặc `--drain` (`stop=drained`). Điểm của mọi phiên được gộp vào cache ở máy trước khi publish checkpoint, và cache đủ cặp thì lệnh ghi biến thể mà không gọi Kaggle. `--force` chấm lại từ đầu: xoá các cặp của run khỏi cache ở máy, phiên đầu bỏ qua checkpoint, kernel cũ và publish lại dataset, các phiên sau chỉ tiếp tục từ điểm của lần chạy này. Mỗi lệnh ghi log có timestamp vào `data/work/logs/rerank/<model>.log`.

`--recover-kernel OWNER/SLUG` (chỉ với `--backend kaggle`) tải output của một kernel đã kết thúc bằng profile có username `OWNER`, kiểm manifest (`rerank_scores`, đúng `--model`, đúng sha256) rồi gộp điểm vào `data/cache/rerank_scores/<model>.jsonl`, không nộp kernel mới. Điểm được khớp theo model, request contract, query và tài liệu, nên cách này dùng được cả khi job identity đã đổi. Khi cache đủ cặp của run, lệnh ghi luôn biến thể.

Rerank chỉ gọi `POST /v1/rerank` với file GGUF bản convert classifier; mỗi request là một câu hỏi cùng các ứng viên chưa có điểm, ở local lẫn Kaggle. `--backend local` dùng service `llama-reranker` của `../compose.local-models.yaml` (chạy cùng `../compose.yaml`): nếu `data/cache/local_profiles/rerank/<model>.json` khớp model, CPU (`/proc/cpuinfo`) và image llama.cpp của file đó thì service được dựng theo profile, không thì theo mặc định của compose.

`--backend local --benchmark` đo từng mức của search space CPU: (`-np`, `-ub`) là (4, 4096), `-b` bằng `-ub`, `-c` bằng `-ub` nhân số slot cộng một, `--threads` 8/12. Mỗi mức dựng lại `llama-reranker`, chạy một nhóm khởi động không tính giờ rồi 6 nhóm câu hỏi × 15 ứng viên chọn phân tầng theo tổng số ký tự. Mức nào xếp hạng ứng viên khác mức hợp lệ đầu tiên thì bị loại (`rank_mismatch`); lệnh chọn p95 thấp nhất (bằng nhau thì số cặp/giây cao hơn), lưu profile và in `selected=`, `latency_p95_seconds=`, `env=`. Chép `env=` vào `.env` ở gốc repo và đặt `RERANK_TIMEOUT_SECONDS` ít nhất gấp đôi `latency_p95_seconds`.

```bash
uv run pharma-lab rerank --run hybrid-qwen4b-v3-p50-k20-rrf2 --backend local --benchmark --model qwen3-reranker:4b-q8_0
```

```bash
uv run pharma-lab rerank --run backend-hybrid-qwen4b-v3-p50-k20-rrf2 --backend kaggle --model qwen3-reranker:4b-q8_0 --kaggle-account auto
uv run pharma-lab metrics --run backend-hybrid-qwen4b-v3-p50-k20-rrf2 --top-k 20
uv run pharma-lab metrics --run backend-hybrid-qwen4b-v3-p50-k20-rrf2 --model qwen3-reranker:4b-q8_0 --top-k 20
```

Report nằm ở `reports/baseline/top<K>-window<N>/` và `reports/rerank/<model>/top<K>-window<N>/`; chạy lại cùng cutoff với input khác thì lệnh dừng, `--force` thay report. Metrics gồm Hit@3/5/10/30, MRR, và với `answer_mode=multi_required`: Multi-section Recall@K, Multi-all-hit@K. `--top-k` không được lớn hơn `candidate-k`. `--gold-only` chấm chỉ theo mục gold, không dùng relevance judgments, và ghi vào `top<K>-gold/`; run trên bundle chia chunk khác mặc định (`bundle rechunk`) phải dùng cờ này.

`pharma-lab metrics select` áp luật chọn retriever và reranker của agent (spec v2 §3.4) lên các cấu hình đã có report cùng cutoff. Mỗi `--config LABEL=RUN[@MODEL]` là một report: không có `@MODEL` là report baseline của run, có thì là report sau reranker đó; liệt kê từ rẻ tới đắt. Ở mỗi giai đoạn, cấu hình dẫn đầu là cấu hình có trung bình `--metric` cao nhất (bằng nhau thì cấu hình đứng trước); nó thắng một cấu hình khác khi khoảng 95% bootstrap ghép cặp 10.000 lần của hiệu nằm trên 0 và p sign-flip ghép cặp, hiệu chỉnh Holm trong giai đoạn, dưới 0,05. Còn hòa thì xét `--secondary` trên các cấu hình hòa; vẫn hòa thì chọn cấu hình rẻ nhất. `--exclude-group` (lặp được) bỏ câu của một `eval_group` khỏi quyết định. Lệnh dừng khi các report khác file golden, chấm bằng judgments khác file judgments hiện tại (chạy lại `pharma-lab metrics --run RUN --force`), hoặc khác tập câu.

```bash
uv run pharma-lab metrics select --top-k 20 --metric hit@20 --secondary hit@5 --exclude-group conversational \
  --config bm25=bm25-v3-k20 --config dense-qwen8b=dense-qwen8b-v3-k20 --config hybrid-qwen8b=hybrid-qwen8b-v3-p50-k20-rrf2
```

`pharma-lab embed queries --backend local|kaggle --model MODEL` tạo cache vector query (`data/cache/query_embeddings/<model-slug>.jsonl`) mà `pharma-lab retrieve` dùng cho `dense` và `hybrid`; `--model` phải trùng model embedding của backend. Candidate `document_text` là `embedding_text` của hit, đúng văn bản reranker của benchmark cũ chấm.

## Chạy theo lô trên Kaggle (e2e, rerank, embedding)

| Command | Việc |
| --- | --- |
| `pharma-lab e2e run --backend kaggle ...` | Chia các cặp (cấu hình, câu) còn thiếu thành shard, mỗi shard một kernel, chạy song song trên các account còn quota và gộp kết quả vào `answers.jsonl` ở máy; chạy lại để nối tiếp. Mã thoát `0` xong, `10` tạm dừng (hết quota, `--drain`, `--max-sessions`), `11` còn cặp kẹt (`--retry-stuck` để thử lại) |
| `pharma-lab e2e status --run NAME --config ...` | Số câu xong/tổng/kẹt từng cấu hình, kernel đang chạy, quota từng account và giờ GPU còn cần |
| `pharma-lab kaggle status` | Kernel đang chạy theo bước và account, quota với giờ reset, dataset credential còn sót |

Cờ chung của `e2e run`, `rerank`, `bundle embed` và `embed queries`: `--kaggle-account auto` (mọi profile `accN`), `accN` hoặc `acc1,acc3`; `--parallel N` (số shard cùng lúc, mặc định hai mỗi account); `--drain` (để kernel đang chạy xong rồi dừng). Riêng `e2e run`: `--llm gemini|opus` cần `--with-proxy-credentials` (tải file credential của proxy lên dataset private của lượt chạy, xoá khi lệnh kết thúc), `--judge` chấm câu mới về, `--latency` là lượt đo `concurrency 1` ghi vào `<run>-c1`. Chi tiết: [E2E evaluation](e2e-evaluation.md), [Local + Kaggle workflow](workflow-local-kaggle.md).

## Runtime profiling trên Kaggle

Stage production tự benchmark một lần nếu chưa có profile hợp lệ và lưu ở `data/cache/kaggle_profiles/<workload>/<model>.json`; profile mất hiệu lực khi model, runtime, topology hoặc search space đổi. Mỗi mức là một cấu hình server đầy đủ (`-np`, `-ub`, số tài liệu mỗi request, số request đồng thời) và server khởi động lại khi đổi mức. Reranker chạy `--reranking --kv-unified -np N -c UB×(N+1) -b UB -ub UB`; tải đo là 32 nhóm câu hỏi × 30 ứng viên chọn phân tầng theo tổng số ký tự, cộng một nhóm khởi động không tính giờ. Mức nào xếp hạng ứng viên khác mức hợp lệ đầu tiên bị ghi `invalid` (`rank_mismatch`), mức chấm thiếu hoặc thừa cặp ghi `score_mismatch`; `max_abs_score_delta` vẫn được ghi cho mọi mức. Stage chọn mức có số cặp/giây cao nhất. Mọi mức đều lỗi thì stage dừng và in trạng thái cùng đuôi log server của từng mức.

## Archive dữ liệu

Mọi file dưới `data/` mà Git bỏ qua (trừ `data/work/`) được lưu trong dataset Kaggle private `<owner>/vipharmind-data-v2`, `<owner>` là username của profile `--kaggle-account`. Mỗi `push` tạo một version mới của dataset; `pull --version N` lấy lại version N (mặc định version mới nhất). `push` đóng gói thành các phần `vipharmind-data-v2.tar.zst.part-NNNN` (tối đa 1.900 MiB mỗi phần) cùng `archive-manifest.json` ghi sha256 từng phần và từng file, dựng ở `data/work/archive/`, rồi tạo dataset hoặc version mới.

```bash
uv run pharma-lab data push --kaggle-account acc1 --message "Rebuild evaluation runs"
uv run pharma-lab data pull --kaggle-account acc1
```

`push` thay toàn bộ archive, nên lệnh dừng và liệt kê các file có trong archive hiện tại mà `data/` đang thiếu; chạy `pull` trước, hoặc thêm `--allow-removal` khi muốn bỏ hẳn các file đó khỏi archive.

`--dataset SLUG` (cả `push` và `pull`) chọn dataset khác `vipharmind-data-v2`, ví dụ `pull --dataset vipharmind-data-v1` để lấy data của v1; tên các phần lấy từ manifest nên archive đẩy dưới tên dataset khác vẫn đọc được. `push` từ chối các dataset đã đóng của v1 (`vipharma-rag`, `vipharmind-data-v1`, `vipharmind-data`).

`pull` tải lại các phần còn thiếu hoặc lệch checksum, kiểm sha256 từng phần và từng file, bỏ qua file đã giống hệt. File đang có mà khác archive thì lệnh dừng và liệt kê; thêm `--force` để ghi đè.

## Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | Stage completed successfully |
| 1 | Runtime or validation failure |
| 2 | Invalid CLI usage |
| 3 | Resumable incomplete stage |
| 130 | Interrupted by the operator |

## Đánh giá end-to-end

Chi tiết trong [e2e-evaluation.md](e2e-evaluation.md).

| Command | Việc |
| --- | --- |
| `pharma-lab e2e golden sample [--seed S] [--force]` | Chọn câu answerable của sáu nhóm luật theo hạn ngạch trong `golden.py` (phân tầng theo intent và answer mode) và 160 cặp multi-turn, ghi `data/evaluation/e2e/authoring/*.todo.jsonl` kèm text section và chunk trọng tâm |
| `pharma-lab e2e golden resample --slots IDS [--per-slot N]` | Đưa N câu chưa dùng cùng tầng cho các slot mà section gold không trả lời câu hỏi, ghi `replacement-NN.todo.jsonl` |
| `pharma-lab e2e golden pharmacist-pack [--golden FILE]` | Ghi gói duyệt toàn bộ golden cho dược sĩ (`authoring/pharmacist/*.md`) và bảng verdict, giữ verdict của câu không đổi nội dung |
| `pharma-lab e2e golden pharmacist-score [--golden FILE]` | Tỉ lệ câu dược sĩ sửa hoặc loại theo tầng (Wilson); complete khi mọi câu có verdict và không còn `fail` |
| `pharma-lab e2e golden multi-hop-candidates` | Liệt kê mọi dòng nhóm `multi_hop` của benchmark làm ứng viên, loại là `query_form`, ghi `authoring/multi-hop.todo.jsonl` |
| `pharma-lab e2e golden check FILE` | Kiểm một lô `*.authored.jsonl` (quote nằm trong section, hành vi theo nhóm, `absent_terms` vắng trong corpus) |
| `pharma-lab e2e golden build` | Kiểm đủ số lượng từng nhóm rồi ghi `golden_e2e.jsonl` và manifest |
| `pharma-lab e2e run --run NAME --config full\|one-step\|no-judge-refine\|no-rephrase\|no-rerank\|no-guard\|bm25\|dense\|hybrid-k60\|closed-book\|react [--pipeline-option KEY=VALUE ...] [--limit N] [--concurrency N] [--deadline-seconds S] [--retry-errors]` | Chạy agent trên bộ golden, ghi `runs/<run>/<config>[+key=value...]/answers.jsonl`; chạy lại để resume |
| `pharma-lab e2e judge --run NAME --config CONFIG_DIR [--judge-model MODEL] [--judge-reasoning none\|low\|medium] [--concurrency N] [--items IDS] [--force]` | Chấm bằng RAGAS và judge cấu trúc, ghi `judgments.jsonl` và `judge.json` |
| `pharma-lab e2e calibration export --run NAME [--seed S] [--config C ...]` | Xuất 50 câu mù mỗi cấu hình (mặc định `full`, `one-step`) để chấm hiệu chỉnh |
| `pharma-lab e2e calibration refresh --run NAME` | Sau khi sửa golden hoặc chạy lại câu trả lời: cập nhật các câu mù đã thay đổi trong mẫu (giữ nguyên mẫu), chuyển điểm cũ của chúng sang `grades.superseded.jsonl` và in danh sách cần chấm lại |
| `pharma-lab e2e calibration score --run NAME` | Tính κ và ρ giữa judge và `calibration/grades.jsonl` (dừng nếu mẫu còn câu đã đổi mà chưa refresh) |
| `pharma-lab e2e decision-probe [--chars 60000] [--bundle DIR] [--backend-env-file FILE]` | Gửi decision model (vai judge, provider `systemone`) một state judge chứa `--chars` ký tự bằng chứng lấy từ các chunk dài nhất của bundle; in số token vào, ký tự mỗi token, giây, phiên bản model và `recommended_max_evidence_chars` (số ký tự đã đo quy về 24.000 token, làm tròn xuống nghìn, không vượt 60.000) |
| `pharma-lab e2e decision-set build --run RUN --model RERANKER [--size 300] [--seed S] [--bundle DIR]` | Chọn 300 câu benchmark (chia đều theo nhóm, bỏ nguồn của golden), lấy top 5 sau rerank của run làm bằng chứng (dựng từ chunk của bundle như `judge_state`), gán nhãn `sufficient` theo độ phủ gold, ghi `data/evaluation/calibration/judge_set.jsonl` |
| `pharma-lab e2e decision-set guard-draft [--count 300] [--seed S]` | LLM viết 300 lượt (150 tấn công) tấn công, ngoài phạm vi và trò chuyện phiếm từ mẫu cố định, ghi `guard_set.todo.jsonl` để tác giả duyệt rồi đổi tên thành `guard_set.jsonl` |
| `pharma-lab e2e decision-set score [--repeats 3]` | Chấm decision model trên tập giữ riêng, ghi từng lệnh gọi vào `decisions.jsonl` (chạy lại thì tiếp tục) và `jev.json` với AUROC, ECE, Brier, `tau`, `block`, `review` |
| `pharma-lab e2e report --run NAME [--latency-run NAME]` | Ghi bảng CSV/LaTeX (cả `cost.csv\|tex`) và phân tích lỗi vào `runs/<run>/reports/`; `--latency-run` lấy mọi số độ trễ từ run concurrency 1 |
| `pharma-lab e2e compare --run-a NAME --run-b NAME [--config CONFIG_DIR] [--config-b CONFIG_DIR]` | So một cấu hình giữa hai run (hoặc hai cấu hình với `--config-b`) trên item chung (sign-flip ghép cặp, Holm); ghi `runs/<B>/reports/compare-<A>-<config>.csv\|tex` |
