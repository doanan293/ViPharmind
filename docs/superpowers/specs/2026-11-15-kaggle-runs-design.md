# Chạy trên Kaggle: local-first, nối lại được, nhiều tài khoản

Ngày: 2026-11-15. Mô tả mã của nhánh `v2.0.0` (commit `9732e8e`). Thay cho các spec và plan Kaggle
cũ (xem Lịch sử quyết định) và cho Phụ lục B của `2026-10-14-paper-v2-design.md`.

## 1. Mục tiêu và phạm vi

`pharma-lab` dùng GPU miễn phí của Kaggle (T4 x2, khoảng 30 giờ GPU mỗi tuần mỗi tài khoản) cho
mọi bước cần GPU của phòng thí nghiệm đánh giá. Ba yêu cầu của An:

1. Ra kết quả nhanh nhất với quota hiện có.
2. Dừng và chạy tiếp lúc nào cũng được, kể cả khi kernel chết giữa chừng hay máy tắt.
3. Đổi tài khoản không mất gì.

Cùng một ràng buộc cứng: không kernel nào mở cổng hay tunnel ra ngoài. Kernel chỉ được tải về
(pip, apt, binary, model) và nói chuyện qua `127.0.0.1`.

Các bước dùng Kaggle:

| Bước | Lệnh | Đơn vị việc |
| --- | --- | --- |
| Embed corpus | `bundle embed --backend kaggle` | văn bản chưa có trong cache embedding |
| Embed truy vấn | `embed queries --backend kaggle` | truy vấn chưa có trong cache |
| Rerank | `rerank --backend kaggle` | cặp (truy vấn, đoạn) chưa có điểm |
| E2E | `e2e run --backend kaggle` | cặp (cấu hình, câu golden) chưa có câu trả lời |
| Đo profile runtime | `*-benchmark`, `auto_profile` | một kernel, không chia shard |

Spec này nói về cách chạy trên Kaggle. Nội dung của từng bước (corpus, retrieval, reranker, harness
e2e, judge) thuộc các spec khác, xem mục 6.

## 2. Thiết kế hiện hành

### 2.1 Nguyên tắc

1. **Trạng thái nằm ở máy.** Sự thật duy nhất là cache cục bộ (`data/cache/text_embeddings/`,
   `data/cache/rerank_scores/<model>.jsonl`, cache embedding truy vấn) và
   `data/evaluation/e2e/runs/<run>/<config>/answers.jsonl` cùng `run.json`. Kaggle chỉ là chỗ tính tạm;
   mất kernel, mất quyền vào tài khoản hay xóa dataset không làm mất kết quả đã về.
2. **Phần còn thiếu luôn tính lại từ trạng thái máy.** Không có "job" cần nhớ. Chạy lại cùng lệnh
   là tự biết còn thiếu gì, nên dừng, nối lại và đổi tài khoản là cùng một thao tác.
3. **Không cổng nào mở ra ngoài kernel.** `tests/integrations/kaggle/test_no_external_exposure.py`
   giữ quy tắc này (Qdrant, llama-server, proxy đều nghe `127.0.0.1`).
4. **Một lệnh** làm cả lập kế hoạch, chạy, thu và gộp.

### 2.2 Lớp điều phối chung (`pharma-lab/src/pharma_lab/integrations/kaggle/`)

| Module | Việc |
| --- | --- |
| `shards.py` | `WorkUnit(key, seconds, group)`, `Shard`, `plan_shards(...)`: hàm thuần, tất định. Mỗi shard vừa một phiên: `(budget - margin - setup) * effective_parallelism`; việc nhỏ hơn chi phí dựng môi trường thì không tách; không trộn `group`; `shard_id` chỉ phụ thuộc tập khóa đơn vị việc. |
| `scheduler.py` | `run_shards(adapter, contexts, registry, settings, ...)`: thread pool chạy shard song song, nhận lại shard của lệnh trước (`_queue_orphans`), chia lại phần chưa giao khi một kernel xong sớm, backoff khi Kaggle trả 429. Dừng với `SchedulerStop`: `nothing-missing`, `complete`, `quota-exhausted`, `drained`, `max-sessions`, `stuck`. Shard hai lần liền không thêm gì thì `stuck` (`ATTEMPTS_BEFORE_STUCK = 2`). |
| `job_registry.py` | `jobs.json` của từng bước (`data/work/e2e-kaggle/<run>/`, `data/work/kaggle-*/<model>/`): shard đã đẩy lên mà chưa thu. Dùng để nối lại kernel và để trừ quota đã cam kết, tính cả shard của bước khác (`shared_registry`). Bản ghi cũ hơn 13 giờ bị bỏ. Mất file chỉ tốn quota, không sai dữ liệu. |
| `sessions.py`, `quota.py` | `reserve_session_account`: đọc `kaggle quota -v` của mọi profile được phép, ưu tiên tài khoản đang chạy kernel của shard (để nối lại), nếu không thì chọn tài khoản còn nhiều giờ nhất sau khi trừ phần đã cam kết, bằng nhau thì `accN` nhỏ hơn. Ngân sách phiên = min(`--budget-seconds`, còn lại - 0,5 giờ), tối thiểu 1 giờ (`QUOTA_MARGIN_SECONDS = 1800`, `MINIMUM_SESSION_SECONDS = 3600`). Hai phiên GPU mỗi tài khoản, mỗi phiên một khóa `data/work/locks/kaggle-accounts/`. |
| `service.py`, `orchestrator.py`, `kernel_reconciler.py` | `run_kaggle_stage`: dựng dataset, đẩy kernel, theo log, tải artifact (kể cả artifact dở) và giao cho `artifact_sink` gộp vào máy trước việc khác. `KernelReconciler` nối lại kernel đang chạy hoặc thu output của kernel lỗi. |
| `dependencies.py`, `checkpoint_inheritance.py` | Dataset `pipeline-input-*` (riêng của một job), `pipeline-static-*` (đầu vào tĩnh theo nội dung, mỗi tài khoản tạo một lần rồi dùng lại), dataset model và bản build llama.cpp. Kế thừa checkpoint giữa tài khoản vẫn còn cho embed và rerank; rerank đưa cache ở máy vào làm một nguồn checkpoint (`RerankCacheCheckpoint`). |
| `workers/` | Mã chạy trong kernel: embed corpus, embed truy vấn, rerank, benchmark, `runtime.py` (`worker_deadline`, quản lý llama-server). Worker rerank khởi động lại llama-server tối đa 3 lần (`MAX_SERVER_RESTARTS`). Không import `config.paths` hay `pharma_agent`. |

Mỗi bước cắm vào bằng một `ShardAdapter` gồm: `missing()` (đơn vị còn thiếu từ kho cục bộ),
`setup_seconds()`, `run_shard(shard, reserved)` (cùng tập đơn vị cho cùng job, để chạy lại thì nối
vào kernel đang chạy), `merge(shard, result)` (idempotent), `preferred_profile(shard, record)`.

| Adapter | File | Ước lượng thời gian |
| --- | --- | --- |
| Embed corpus | `embeddings/shards.py` | theo số ký tự, `SETUP_SECONDS = 300` |
| Embed truy vấn | `evaluation/query_embedding_shards.py` | `SETUP_SECONDS = 300` |
| Rerank | `evaluation/rerank_shards.py` | giây mỗi cặp, mặc định 1 giây; chỉ gửi các cặp cache còn thiếu |
| E2E | `e2e/kaggle_shards.py` | `latency_seconds` của các câu đã có, mặc định 60 giây mỗi lượt; `SETUP_SECONDS = 1800` |

### 2.3 Bước e2e

**Trong kernel** (stage `E2E_RUN`, `integrations/kaggle/e2e_stage.py`, `e2e/kernel_worker.py`,
`e2e/kernel_env.py`): kernel cài Postgres (apt) và Qdrant `v1.19.1`, import bundle corpus, mở
llama-server trên localhost và chạy đúng harness e2e của máy.

- Bố cục máy chủ (bố cục A, bố cục duy nhất hiện có): LLM `qwen3.5:9b-q8_0` ở GPU0 cổng 11434,
  reranker `qwen3-reranker:4b-q8_0` ở GPU1 cổng 11435, embedding `qwen3-embedding:4b-q8_0` trên CPU cổng
  11436 (truy vấn ngắn, hai slot). Mọi model tự host đều Q8_0.
- `e2e_job.json` mang danh sách cặp của shard; harness chỉ chạy các cặp đó, nhận `--pipeline-option`.
- Kernel biết hạn phiên (`worker_deadline`): tới hạn thì ngừng nhận câu mới, chờ câu đang chạy, đóng
  gói rồi thoát. Cứ 300 giây (`SNAPSHOT_SECONDS`) kernel ghi lại `e2e_output.tar` bằng ghi tạm rồi
  `os.replace`, nên kernel bị kill vẫn để lại output gần nhất. Nghiệm thu đã xác nhận Kaggle giữ output
  của kernel trạng thái ERROR.
- `run.json` của shard ghi khối `software`: sha256 từng file model, bản `llama-server`, bản proxy.

**Ở máy** (`e2e/work_state.py`, `e2e/kaggle_launch.py`, `e2e/kaggle_run.py`):

- Tập câu của run là `select_items(golden, limit, category)` như harness. Một cặp còn thiếu khi chưa
  có bản ghi, bản ghi cuối là `superseded`, hoặc bản ghi cuối là `error` có thể thử lại và chưa quá 3
  lần (`MAX_FAILURES = 3`). Quá 3 lần thì cặp "kẹt"; chỉ chạy lại với `--retry-stuck`.
- Gộp chỉ nhận `<config>/answers.jsonl` và `<config>/run.json` trong tar, nối thêm dòng mới, bỏ dòng
  JSONL cụt, không để bản `error` che bản hoàn thành. Danh tính `run.json` của shard phải khớp run ở
  máy; khác sha256 model hoặc bản `llama-server` thì từ chối, khác bản proxy thì chỉ cảnh báo.
- Mặc định một phiên 3 giờ (`DEFAULT_BUDGET_SECONDS`), khoảng 1,5 giờ cho các lượt (`SHARD_WORK_SECONDS
  = 5400`). `--parallel` mặc định hai shard mỗi tài khoản.
- Mã thoát: 0 xong, 10 tạm dừng (hết quota, `--drain`, `--max-sessions`; chạy lại cùng lệnh để tiếp),
  11 có cặp kẹt.
- `e2e status --run R --config C...`: xong/tổng theo cấu hình, số cặp kẹt, kernel đang chạy, ước lượng
  giờ GPU còn cần.
- `--latency`: một cấu hình, một kernel, concurrency 1, ghi vào run `<run>-c1`. Lát cần hơn một phiên
  thì lệnh từ chối.
- `--judge` (tùy chọn) chấm ở máy ngay khi mỗi shard về, với `--judge-model` và `--judge-reasoning`;
  lỗi của judge không chặn việc gộp.

**Model thương mại trong kernel** (`e2e/llm_presets.py`, `e2e/proxy_kernel.py`,
`e2e/proxy_credentials.py`): `--llm qwen|gemini|opus`. Với `gemini` và `opus`, kernel tải
`cli-proxy-api` 8.0.28, ghi config với `host: 127.0.0.1`, chạy ở `127.0.0.1:8317`; harness dùng cùng
biến môi trường như ở máy.

- Credential chỉ lên Kaggle khi có `--with-proxy-credentials` ở từng lần chạy; lệnh in tên và loại
  file sẽ tải, chỉ tải loại cần cho preset (`--proxy-credential FILE` để chọn từng file).
- Credential đi bằng dataset private `pipeline-cred-*` ở tài khoản chạy shard, xóa sau khi thu kết quả
  (bỏ qua Ctrl-C lần hai khi đang xóa, thử lại 3 lần). Không bao giờ vào git, `data/`, archive hay log.
  `kaggle status` liệt kê dataset credential còn sót kèm lệnh xóa.
- Trần request đồng thời trên mọi kernel của một run: Gemini 4, Opus 2 (`max_in_flight`). Lệnh hạ
  concurrency và số shard song song cho vừa trần.

### 2.4 Rerank, embed corpus, embed truy vấn

Cùng scheduler, cùng cờ: `--kaggle-account auto|accN|acc1,acc3` (mặc định `auto`), `--parallel N`,
`--max-runs N`, `--drain`, `--budget-seconds` (mặc định 21.600 giây). Artifact của mọi shard, kể cả
khi kernel dừng giữa chừng, được gộp vào cache ở máy ngay khi về. Lệnh dừng với mã 3 khi chưa đủ (hết
quota thì kèm `stop=quota-exhausted` và bảng quota có `refresh_at`).

Riêng rerank: log bền `data/work/logs/rerank/<model>.log` (tài khoản, quota trước và sau, kernel, số
cặp, lỗi, lý do dừng); `rerank --recover-kernel OWNER/SLUG` gộp điểm của một kernel đã xong mà lệnh
không còn nối vào được (ví dụ job identity đã đổi), theo khóa bản ghi.

### 2.5 Tài khoản và dataset

- Profile trong `pharma-lab/.env`: `KAGGLE_ACC<N>_USERNAME`, `KAGGLE_ACC<N>_API_TOKEN`,
  `KAGGLE_ACCOUNT_DEFAULT`, `KAGGLE_SHARED_OWNER`.
- Dataset model và bản build llama.cpp do profile của `KAGGLE_SHARED_OWNER` tạo, để công khai để mọi
  tài khoản mount (trọng số open-weight). Input, đầu vào tĩnh, checkpoint và credential luôn private
  theo tài khoản chạy; shard chuyển sang tài khoản khác thì tài khoản đó tự upload bản của mình.
- `pharma-lab kaggle status`: kernel đang chạy theo bước và tài khoản (đọc mọi `jobs.json`), quota GPU
  và giờ reset, dataset `pipeline-cred-*` còn sót. Tài khoản lỗi API chỉ làm dòng của nó ghi
  `unavailable`.
- Lệnh chạy lâu chạy trong tmux, mỗi job một cửa sổ. Ctrl-C chỉ dừng lệnh; kernel vẫn chạy và lần sau
  lệnh nối vào. Kaggle CLI không có lệnh hủy kernel.

Hướng dẫn thao tác: `pharma-lab/docs/guides/workflow-local-kaggle.md` (embed, rerank, mục 7 về nhiều
tài khoản), `pharma-lab/docs/guides/e2e-evaluation.md` (e2e), `pharma-lab/docs/guides/cli-reference.md`.

### 2.6 Số đo nghiệm thu (job Kaggle thật, 2026-10-23)

- Dựng môi trường e2e khoảng 8 phút (venv 5 s, Postgres 47 s, Qdrant 3 s, model server 157 đến 273 s,
  nhập corpus 220 s), không phải nửa giờ như ước lượng ban đầu.
- Ép dừng theo hạn, Ctrl-C rồi nối lại, đổi tài khoản, ba tài khoản song song (300 câu, ba shard 84,
  83, 83), Gemini qua proxy trong kernel, rerank, embed truy vấn, embed corpus 13.408 văn bản trên ba
  tài khoản (cosine so với cache cũ từ 0,9995): đều đạt.
- Chưa thử xong: câu trả lời đầy đủ của Opus (tài khoản Claude bị giới hạn tốc độ lúc nghiệm thu),
  `--judge` với model judge chạy được trên proxy.

## 3. Ngoài phạm vi

- Tunnel, mở cổng, phục vụ model ra ngoài kernel.
- Resume bên trong một kernel; chia một câu hỏi giữa nhiều kernel.
- Checkpoint dataset phía Kaggle cho e2e (trạng thái đã ở máy).
- Khóa API trực tiếp. Chỉ decision model Jev dùng OpenRouter, ngoài Kaggle (quyết định 2026-10-26).
- Hoãn tới khi có số đo cho thấy cần: bố cục B (hai bản LLM, mỗi bản một T4, cho cấu hình không
  rerank), hàng đợi chung giữa các cấu hình trong kernel, dataset "toolchain" đóng gói sẵn bánh xe
  Python, Qdrant và Postgres. Ngưỡng cho toolchain là dựng môi trường quá 15 phút; số đo là 8 phút
  nên chưa cần.

## 4. Việc còn mở

Plan `docs/superpowers/plans/2026-11-15-kaggle-runs-followups.md`:

- Nối lại shard mà tài khoản đã ghi trong `jobs.json` không còn nằm trong `--kaggle-account` thì lỗi
  `generator raised StopIteration` (`sessions.reserve_session_account` gọi `next(...)` trên quota của
  tài khoản không được đọc). Tool tự chia lại nên không chặn, nhưng nên sửa.
- Nghiệm thu còn thiếu: Opus đầy đủ, `--judge` với judge chạy được.
- Dọn dataset `pipeline-static-*`, `pipeline-input-*` còn sót trên Kaggle (chờ An quyết).

## 5. Lịch sử quyết định

| Ngày | Quyết định | Thay cho | Lý do | Nguồn |
| --- | --- | --- | --- | --- |
| 2026-09-15 | Rerank chạy nhiều phiên tuần tự trên tài khoản còn nhiều quota nhất (`run_account_sessions`, `--kaggle-account auto`), khóa theo tài khoản, cache ở máy là nguồn gốc và được đưa vào kế thừa checkpoint, dataset dependency do `KAGGLE_SHARED_OWNER` tạo, worker khởi động lại llama-server tối đa 3 lần, log bền, `--recover-kernel`. | Một tài khoản cố định, tối đa 10 phiên, phải chạy lại bằng `acc1` khi thiếu dataset. | Một model rerank cần nhiều phiên GPU; đổi tài khoản không được mất điểm. Phần lớn còn trong mã; vòng lặp tuần tự sau bị scheduler song song thay. | `f9fc933:pharma-lab/docs/superpowers/plans/2026-09-15-kaggle-quota-sessions.md` (bản gốc `664c3dd:seed-pipeline/docs/superpowers/plans/2026-09-15-kaggle-quota-sessions.md`); thiết kế ở §4.8–4.9 của `native-rerank-optimisation-design`, xem spec `corpus-data-pipeline`; mã `4d806a1` |
| 2026-09-17 | E2E gọi model tự host qua tunnel: kernel `rerank-serve` và `llm-server` chạy llama-server sau proxy round-robin và cloudflared, máy local gọi vào. Spec paper v2 ban đầu giả định mỗi model một server riêng trên một tài khoản. | Reranker chạy trên CPU laptop (khoảng 10 phút mỗi request 40 tài liệu). | Cần GPU cho reranker và LLM khi harness chạy ở máy. | `6dac0e6`, `61b0d86` (commit); `0b2a5b3:docs/superpowers/specs/2026-10-14-paper-v2-design.md` §2.1b |
| 2026-10-20 | Bỏ hẳn tunnel. `e2e run --backend kaggle` chạy cả agent trong một kernel (stage `E2E_RUN`): Postgres, Qdrant, ba llama-server trên localhost, harness. Một job là một phiên kernel, hết giờ thì chạy lại cả job; thư mục đích đã có `answers.jsonl` thì từ chối. Gemini có reranker không chạy trên Kaggle. Mặc định tài khoản trong `.env`, không `auto`. | Tunnel (2026-09-17). | 2026-10-19 tài khoản acc2 bị Kaggle khóa vì "resource abuse" do notebook `rerank-serve` mở tunnel. | `f582acc:docs/superpowers/specs/2026-10-20-kaggle-batch-e2e-design.md`; `9732e8e:docs/superpowers/plans/2026-10-20-kaggle-batch-e2e.md`; mã `80de8ef` |
| 2026-10-23 | Mọi bước Kaggle theo kiểu local-first: phần thiếu tính từ máy, chia shard, chạy song song hai phiên mỗi tài khoản trên nhiều tài khoản, nối lại và đổi tài khoản không cần thao tác; kernel biết hạn phiên và chụp output định kỳ; `cli-proxy-api` chạy trong kernel cho Gemini và Opus. Mặc định `--kaggle-account auto`. | Một kernel một job không resume (2026-10-20); vòng phiên tuần tự của rerank (2026-09-15); giới hạn "Gemini có reranker không chạy được". | Ngày 2026-10-22 Kaggle gỡ khóa và gọi là "false positive", nhưng thực thi là tự động và mỗi vi phạm chỉ kháng cáo một lần, nên An chốt: mọi thứ trong kernel, không cổng. Cần ba điều: nhanh, dừng và nối lại dễ, đổi tài khoản dễ. Một job một phiên không resume thì kernel chết là mất hết. | `f582acc:docs/superpowers/specs/2026-10-23-kaggle-resumable-runs-design.md`; `9732e8e:docs/superpowers/plans/2026-10-23-kaggle-resumable-runs.md`; mã từ `bd5c61b` |
| 2026-10-23 | Cho phép đưa mọi file credential trong volume proxy lên Kaggle, kèm các biện pháp: cờ theo từng lần chạy, dataset private xóa sau khi thu, trần đồng thời theo nhà cung cấp. | Credential chỉ ở máy. | An chấp nhận rủi ro sau khi được nêu. | như dòng trên, §9 |
| 2026-10-23 | Sau nghiệm thu: trần Gemini 4 request (từ 8), Opus 2; Qdrant trong kernel nghe `127.0.0.1`; tên binary proxy là `cli-proxy-api`; thêm `--judge-model`, `--judge-reasoning`. | Giá trị ban đầu của spec. | Lỗi chỉ lộ ra ở job thật (8 request làm Gemini trả 429 `model_cooldown`, Qdrant nghe `0.0.0.0`...). | `f582acc:docs/superpowers/specs/2026-10-23-kaggle-resumable-runs-design.md` (Kết quả nghiệm thu); `f0ffa88`, `be288c8`, `4433434` |
| 2026-10-24 | Spec resumable gộp thành Phụ lục B của spec paper v2; spec batch e2e bị xóa. | Hai spec riêng. | Một spec paper v2 có bảng tiến độ. | `414e317` |
| 2026-10-26 | Shard rerank chỉ gửi các cặp cache còn thiếu. Mọi model tự host (gồm rewriter Qwen của D5) chạy trên Kaggle; chỉ Jev qua OpenRouter. | Gửi cả nhóm truy vấn. | Tiết kiệm giờ GPU; quy tắc hạ tầng của An. | `85022c1`, `1b73f5b` |
| 2026-11-15 | Gom các spec và plan Kaggle vào file này. | Phụ lục B của spec paper v2 và năm file nguồn. | Một nơi, khớp mã `v2.0.0`. | file này |

Chi tiết đã bỏ khi gom: hằng số và tên lệnh của đường tunnel; bố cục GPU ban đầu (embedding F16 trên
GPU1, nay Q8_0 trên CPU); ngân sách phiên e2e "khoảng 2 giờ" và 7.200 giây trong plan (mã dùng phiên
3 giờ với khoảng 1,5 giờ việc); "kẹt" của scheduler sau 2 lần không tiến triển khác với "kẹt" của
cặp e2e sau 3 lần lỗi, cả hai còn trong mã.

## 6. Liên kết

- `2026-11-15-evaluation-design.md`: harness e2e, golden, judge, benchmark và cách chọn cặp
  retrieval mà các run trên Kaggle dùng.
- `2026-11-15-corpus-data-pipeline-design.md`: corpus, bundle, cache embedding và rerank, thiết kế
  rerank native (bản gốc §4.8–4.9 của quota sessions).
- `2026-11-15-soict-paper-design.md`: paper v2 (spec cũ `2026-10-14-paper-v2-design.md` chứa Phụ lục B
  mà file này thay thế), camera-ready.
- `2026-11-15-architecture-rules-design.md`: tầng import (`integrations/kaggle` không import `e2e`,
  `evaluation`, `embeddings`), vị trí test.
