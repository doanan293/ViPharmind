# Spec: Mọi bước chạy trên Kaggle theo kiểu local-first, nối lại được, chia nhiều tài khoản

Ngày: 2026-10-23. Trạng thái: chờ duyệt. Nhánh: `v2.0.0`.
Thay phần "Đường gọi model" của `2026-10-14-paper-v2-design.md` (§2.1b, §2.5) và kế hoạch chạy trên
Kaggle của spec đó; không đụng `camera-ready`, tag `v1.1.0` hay data của bài đã nộp.

## 0. Vì sao

Ngày 2026-10-19 account acc2 bị khoá vì một notebook `rerank-serve` mở tunnel cloudflared. Ngày
2026-10-22 Kaggle gỡ khoá và gọi đó là "false positive" của hệ thống tự động. Điều khoản của Kaggle
không nhắc tunnel (đã đọc Terms, Community Guidelines, Notebooks docs ngày 2026-10-23), nhưng thực thi
là tự động và theo quyết định của họ, và mỗi vi phạm chỉ kháng cáo một lần. **Quyết định của người dùng
(2026-10-23): mọi thứ chạy trong kernel, không tunnel, không mở cổng.** Test
`tests/integrations/kaggle/test_no_external_exposure.py` giữ quy tắc này.

**Phạm vi (người dùng, 2026-10-23): cơ chế áp dụng cho mọi bước dùng Kaggle**, không chỉ bước e2e cuối:
embed corpus, embed truy vấn, rerank, các lượt đo profile và e2e. Phần e2e (§4.1 đến §4.8) là bộ
chuyển đổi khó nhất vì hiện chưa có resume nào; §4.9 nêu lớp điều phối chung và cách từng bước còn lại
cắm vào.

Spec v2 gốc được viết trước đó nên vẫn giả định mỗi model là một server riêng trên một account và
một tunnel nối về máy. Cần thiết kế lại cách chạy sao cho đạt ba điều người dùng yêu cầu:

1. **Ra kết quả nhanh nhất** với quota GPU hiện có (30 giờ mỗi tuần mỗi account; ngày 2026-10-23
   còn khoảng 6 đến 8 giờ mỗi account, reset sáng 2026-10-24).
2. **Dừng và chạy tiếp dễ dàng**, bất kỳ lúc nào, kể cả khi kernel chết giữa chừng.
3. **Đổi account dễ dàng** mà không mất gì và vẫn làm tiếp.

## 1. Hiện trạng (đã đọc code)

Stage `E2E_RUN` hiện có (`integrations/kaggle/e2e_stage.py`, `e2e/kernel_worker.py`,
`e2e/kernel_harness.py`, `e2e/kaggle_run.py`) chạy cả agent trong một kernel: LLM Qwen3.5-9B Q8_0 ở
GPU0, reranker Q8_0 ở GPU1, embedding trên CPU, Postgres và Qdrant cài ngay trong kernel, harness
`run_e2e` gọi qua localhost. Điểm yếu:

- Một lệnh là **một kernel trên một account**. Worker chỉ đóng gói `e2e_output.tar` **sau khi harness
  chạy xong**; kernel chết, hết giờ hay hết quota giữa chừng thì không có gì để tải về.
- Worker **không biết hạn của phiên** (rerank dùng `worker_deadline`, e2e thì không) và không bao giờ
  ghi kết quả dở.
- Kernel mới luôn bắt đầu từ thư mục trống: không nhận lại phần đã làm.
- CLI từ chối chạy nếu thư mục đích đã có `answers.jsonl` (`check_targets`) và báo lỗi, không ghi gì,
  nếu kernel chưa xong mọi câu. Gọi `run_kaggle_stage(max_runs=1, resume_remote=False)`.
- Mỗi phiên tốn thời gian dựng môi trường (pip, apt Postgres, tải Qdrant, nạp corpus, khởi động ba
  server). Chưa có số đo; ước lượng khoảng nửa giờ.
- `kernel_harness` không nhận `--pipeline-option`, nên các cấu hình biến thể của v2 (`guard=false`,
  `refine_threshold`, `refine_mode`...) chưa chạy được trên Kaggle.

Hạ tầng đã có và dùng lại được (pipeline rerank đang dùng đúng mô hình này, xem
`evaluation/rerank_service.py`, `rerank_cache_checkpoint.py`):

- `sessions.run_account_sessions`, `reserve_session_account(_waiting)`, `QuotaExhausted`,
  `StopReason`: chọn account theo quota còn lại, khoá theo account giữa các lệnh local, tự xoay
  account, dừng khi hết quota hoặc không tiến triển. Kaggle cho mỗi account hai phiên GPU batch cùng
  lúc (`SESSION_CAPACITY_MARKER`).
- `LocalCheckpointSource` và `artifact_sink` của `run_kaggle_stage`: coi tiến độ nằm ở máy là một
  checkpoint và nhận kết quả về máy trước khi làm việc khác.
- `KernelReconciler.attach_or_recover` và `CloudArtifact.allow_partial`: nối lại kernel đang chạy,
  nhận lại output của kernel lỗi, chấp nhận artifact chưa đủ.
- `workers/runtime.worker_deadline`: hạn dừng nhận việc mới, chừa biên để xả việc đang chạy.

### 1.1 Các bước Kaggle hiện có (đã đọc `StageName` và nơi gọi `run_kaggle_stage`)

| Bước (lệnh) | Việc còn thiếu tính ở máy | Resume | Xoay account | Song song nhiều account |
| --- | --- | --- | --- | --- |
| Embed corpus (`bundle embed --backend kaggle`) | Có: chỉ gửi văn bản chưa có trong cache (`missing_inputs.jsonl`) | Có (checkpoint) | Không: gắn một account (`hold_pinned_account`) | Không |
| Embed truy vấn (`embed queries --backend kaggle`) | Có: chỉ gửi truy vấn chưa có (`*.missing.jsonl`) | Có | Không: gắn một account | Không |
| Rerank (`rerank --backend kaggle`) | Có: cache rerank là checkpoint cục bộ | Có | **Có** (`run_account_sessions`, tuần tự) | Không |
| Đo profile (`*-benchmark`, `auto_profile`) | Không áp dụng (một lượt đo) | Không áp dụng | Có (`reserve_session_account_waiting`) | Không áp dụng |
| e2e (`e2e run --backend kaggle`) | **Không** | **Không** | Không | Không |

Ba bước nặng nhất (rerank, embed corpus, e2e) đều có thể tách theo "đơn vị việc còn thiếu", nên đều
hưởng lợi từ chia shard song song nhiều account. Các lượt đo profile là một kernel duy nhất nên giữ nguyên.

## 2. Nguyên tắc

1. **Trạng thái nằm ở máy.** Sự thật duy nhất là `data/evaluation/e2e/runs/<run>/<config>/answers.jsonl`
   (cùng `run.json`). Kaggle chỉ là chỗ tính toán tạm. Mất kernel, mất quyền vào account hay xoá
   dataset không làm mất kết quả đã tải về.
2. **Phần còn thiếu luôn tính lại từ trạng thái máy.** Không có "job" cần nhớ để chạy tiếp: chạy lại
   cùng lệnh thì tự biết còn thiếu gì. Vì vậy dừng, nối lại và đổi account là cùng một thao tác.
3. **Không cổng nào mở ra ngoài kernel.** Internet chỉ để tải về. Dataset đầu vào của một job là
   private theo account chạy, không chứa khoá API.
4. **Một lệnh duy nhất** (`e2e run --backend kaggle`) làm cả việc lên kế hoạch, chạy, thu và gộp.

## 3. Hành vi người dùng thấy

```bash
pharma-lab e2e run --backend kaggle --run e2e-v2-qwen9b \
  --config full --config one-step [--category ...] [--limit N] \
  [--pipeline-option guard=false ...] \
  [--kaggle-account auto | acc1,acc3]  [--parallel N]  [--budget-seconds S]  [--max-sessions K]
pharma-lab e2e status --run e2e-v2-qwen9b
```

- Lệnh tính phần thiếu theo từng cấu hình, chia thành các **shard**, đẩy mỗi shard lên một kernel của
  một account còn quota, chạy song song, thu kết quả về, gộp vào máy, rồi lặp cho tới khi hết việc,
  hết quota hoặc tới `--max-sessions`.
- **Dừng:** Ctrl-C hoặc tắt máy bất kỳ lúc nào. Kernel đang chạy vẫn chạy tiếp. Chạy lại cùng lệnh
  sẽ nối lại kernel đó (`attach`) hoặc thu kết quả của nó, rồi tạo shard mới cho phần còn thiếu.
- **Hết quota:** lệnh in bảng quota từng account, giờ reset, số câu còn thiếu theo cấu hình, rồi thoát
  với trạng thái "tạm dừng" (không phải lỗi). Chạy lại sau khi quota reset.
- **Đổi account:** không cần thao tác. `--kaggle-account` chỉ giới hạn tập account được phép dùng;
  `auto` là mọi account có profile. Không có trạng thái nào gắn với một account.
- `e2e status` in bảng cấu hình × (xong/tổng), các kernel đang chạy (account, shard, giờ đẩy lên),
  quota của từng account, và ước lượng số giờ GPU còn cần.

## 4. Thiết kế

### 4.1 Gộp kết quả vào máy (nguồn sự thật)
- Mỗi cặp (cấu hình, câu) giữ **một bản ghi cuối**. Bản hoàn thành không bao giờ bị bản `error` ghi
  đè; hai bản hoàn thành thì giữ bản mới hơn. Gộp hai lần cho cùng kết quả (idempotent).
- **Tập câu của một run** là đúng kết quả `select_items(golden, limit, category)` mà harness dùng
  (lọc theo nhóm rồi `spread` theo `--limit`). Planner và `status` gọi chính hàm đó. Đổi `--limit`
  hay `--category` ở lần chạy sau chỉ đổi tập "cần có", không bao giờ xoá bản ghi đã có.
- Bản ghi cuối của một câu là **dòng cuối** của câu đó trong `answers.jsonl` (file nối thêm, đúng như
  `JsonlStore.latest()`).
- Một cặp **còn thiếu** khi: không có bản ghi; hoặc bản ghi cuối có `status = superseded` (câu golden
  đã sửa, luôn chạy lại như `run_items`); hoặc bản ghi cuối là `error` có `retryable` và **chưa quá 3 lần
  thất bại**. Số lần thất bại đếm bằng số dòng `error` của câu đó trong file, không thêm trường mới.
  Quá 3 lần thì cặp ở trạng thái `kẹt`: `status` liệt kê riêng, planner không đưa vào shard trừ khi
  người dùng thêm `--retry-stuck`. Mục đích là một câu lỗi cố định không đốt quota mãi.
- `extract_outputs` giữ luật hiện nay (chỉ nhận `<config>/answers.jsonl` và `run.json`, từ chối mọi
  thành viên khác) nhưng **gộp** thay vì từ chối thư mục đã có `answers.jsonl`.
- Trước khi gộp, kiểm danh tính: `run.json` của shard phải khớp `run.json` của cấu hình trên máy
  (golden sha256, release, settings, pipeline). Khác thì dừng với thông báo rõ. Commit khác nhau chỉ
  cảnh báo.

### 4.2 Chia shard
- Đơn vị việc là cặp (cấu hình, câu). Một shard gồm nhiều cấu hình **cùng bố cục máy chủ** trên cùng
  một lát câu hỏi, để các cấu hình dùng chung một lần dựng môi trường.
- Bố cục A (có rerank): LLM ở GPU0, reranker ở GPU1, embedding trên CPU (như hiện nay). Đây là bố
  cục duy nhất của **giai đoạn 1**.
- Bố cục B (**giai đoạn 2, chỉ làm khi job thử cho thấy LLM là điểm nghẽn**): cấu hình không rerank
  (`no-rerank`, `no-guard-no-rerank`, `closed-book`) chạy hai bản LLM, mỗi bản một T4, chia request
  bằng một proxy round-robin nhỏ **chỉ nghe trên `127.0.0.1`** trong kernel. Planner không trộn hai
  bố cục trong một shard. Bố cục được ghi vào `run.json` của cấu hình (không thuộc danh tính, vì hai
  bản Q8_0 cho cùng câu trả lời); lệnh gộp không chặn theo bố cục, nhưng phép đo độ trễ (§4.7) cố định
  bố cục.
- Kích thước shard bị chặn bởi **ngân sách thời gian**, không phải số cặp cố định:
  `(tổng giây ước lượng của các cặp ÷ độ song song hiệu dụng) + thời gian dựng môi trường + biên ≤
  budget_seconds`. Ước lượng giây mỗi lượt theo (cấu hình, nhóm câu) lấy từ trường `latency_seconds`
  trong các `answers.jsonl` đã có trên máy (các run Qwen cũ nằm ở
  `data/evaluation/e2e/runs/e2e-qwen35-9b/*/answers.jsonl`); chưa có thì dùng hằng số mặc định, sau
  mỗi shard xong ước lượng được cập nhật từ chính kết quả. Cùng đầu vào cho cùng cách chia (tất định).
  Không chia quá nhỏ vì mỗi shard trả lại chi phí dựng môi trường.
- Số shard chạy song song là `min(--parallel, số account còn quota)`; mặc định `--parallel` bằng số
  account được phép dùng, mỗi account **một shard một lúc** (mặc định của mình, giảm số phiên đồng
  thời trên mỗi account; đổi bằng `--parallel` lớn hơn).

### 4.3 Phía kernel (`kernel_worker`, `kernel_harness`)
- `e2e_job.json` mang danh sách cặp (cấu hình, câu) của shard. Harness chỉ chạy các cặp đó (thêm bộ
  lọc theo `item_id`; `select_items` hiện chỉ lọc theo nhóm và `--limit`).
- **Hạn phiên:** dùng `worker_deadline`. Tới hạn thì ngừng nhận câu mới, chờ các câu đang chạy
  (tối đa `deadline_seconds` của lượt), đóng gói và thoát sạch.
- **Chụp định kỳ:** cứ khoảng 5 phút hoặc 25 câu, worker ghi `e2e_output.tar` và manifest (completion)
  vào thư mục output bằng ghi tạm rồi `os.replace`. Nhờ đó một kernel bị kill hay hết giờ vẫn để lại
  output gần nhất. Chu kỳ là một tham số của job (`snapshot_seconds`, mặc định 300, `0` tắt hẳn) nên
  có thể gỡ mà không phải thiết kế lại.
  *Giả định cần kiểm chứng bằng job thật:* Kaggle giữ `/kaggle/working` của kernel trạng thái ERROR.
  Code hiện có (`attach_or_recover`, `ArtifactContractError` với `KernelStatus.ERROR`) đã xử lý trường
  hợp này. Nếu giả định sai, chụp định kỳ không cứu được kernel bị kill, và chỉ còn **hạn phiên** bảo vệ:
  vì vậy mặc định giữ ngân sách phiên của e2e hiện nay (3 giờ) với biên của `worker_deadline`, không
  nới ra. Phần mã được xây và kiểm thử đơn vị trước; bước kiểm chứng bằng job thật là cổng chấp nhận
  cuối cùng (§7).
- Completion của artifact: `total` là số cặp của shard, `complete` là số cặp có bản ghi không phải
  `error`. Đã có `completed_answers`.
- Truyền `--pipeline-option` vào harness (nhãn thư mục cấu hình `full+guard=false` như chạy local);
  kernel_env đã có vai `AGENT` nên cấu hình `react` chạy được.
- Ghi mốc thời gian từng bước dựng môi trường vào log và telemetry để đo và tối ưu sau này.

### 4.4 Điều phối phía máy
- Module mới điều phối (tên do builder đặt) thay `run_on_kaggle`: tính phần thiếu, lập shard, chạy
  thread pool; mỗi luồng: `reserve_session_account` (khoá theo account, kiểm quota) → `run_kaggle_stage`
  cho shard (`resume_remote=False`, `artifact_sink` ghi vào máy) → gộp → trả account.
- File trạng thái `data/work/e2e-kaggle/<run>/jobs.json` ghi các kernel đang chạy (account, tham chiếu
  kernel, các cặp của shard, giờ đẩy lên). Khi CLI sống lại, nó đọc file này để `attach` hoặc thu
  kết quả của từng kernel trước khi lập shard mới; nếu file mất, kernel mồ côi chỉ tốn quota, không
  làm sai dữ liệu vì mọi thứ tính lại từ trạng thái máy.
- Dùng lại `QuotaExhausted`, `KaggleSessionCapacityReached`, chờ khi account đang bị lệnh local khác
  giữ. Thêm backoff khi Kaggle trả 429 (đã gặp khi tạo dataset liên tiếp).
- **Không dùng checkpoint dataset phía Kaggle cho e2e.** Trạng thái đã nằm ở máy nên không cần kế thừa
  checkpoint giữa account (`checkpoint_inheritance`), và không để lại dataset thừa trên account.
  (Quyết định của mình, dễ đổi: nếu sau này muốn resume trong lúc máy tắt, thêm sau.)

### 4.5 Tốc độ (xếp theo tác dụng)
1. **Shard song song trên nhiều account** (chia thời gian thực cho số account).
2. **Nhiều cấu hình trong một kernel** để chia sẻ một lần dựng môi trường.
3. **Bố cục B** (hai bản LLM) cho cấu hình không cần reranker.
4. **Giảm thời gian dựng môi trường:** bước đầu tiên là *đo*. Nếu vượt 15 phút, đóng gói bánh xe
   Python, nhị phân Qdrant và gói Postgres vào một dataset "toolchain" private để kernel khỏi tải. Chỉ
   làm nếu số đo cho thấy đáng.
5. Judge và báo cáo chạy ở máy song song với kernel, không tốn quota (quy trình hiện có, chưa tự động
   hoá trong lần này).

### 4.6 An toàn
- Giữ `test_no_external_exposure.py`. Không thêm công cụ tunnel, cổng nghe ngoài `127.0.0.1`.
- Dataset đầu vào private theo account chạy; `jobs.json` và log không chứa khoá API.

### 4.7 Đo độ trễ
Độ trễ chỉ so giữa các kiến trúc trên cùng một model (spec v2 §2.5). Chạy riêng một **lượt đo**
(`--latency`): một shard duy nhất, `--concurrency 1`, bố cục A cố định, trên một lát câu hỏi `spread`
(kích thước do người dùng chọn, xem §9), mỗi cấu hình một lượt. Kết quả vào run `<run>-c1`, đúng chỗ mà
`e2e report --latency-run` đang đọc. Chất lượng không lấy từ lượt đo. Chạy một lượt đo nhiều shard hay
nhiều bố cục là sai thiết kế nên planner từ chối.

### 4.8 Model thương mại: `cli-proxy-api` chạy **trong kernel**

Không hạn chế thí nghiệm: Gemini 3.8 Flash, Claude Opus 5.5 và judge `gemini-3.1-flash-lite` chạy trong
kernel cùng reranker GPU và embedding, chia shard như Qwen. Cách làm (người dùng đồng ý đưa file
credential của proxy lên Kaggle, 2026-10-23):

- **Worker dựng proxy trong kernel:** tải bản `CLIProxyAPI_8.0.28_linux_amd64.tar.gz` (đã có trên
  GitHub releases, 23 MB; kết nối đi ra) và kiểm checksum; ghi `config.yaml` từ
  `devops/cli-proxy-api/config.yaml` với `host: 127.0.0.1` và `auth-dir` trỏ vào thư mục tạm quyền
  `0700`; chép các file credential vào đó (quyền `0600`); chạy ở `127.0.0.1:8317`. Harness dùng đúng các
  biến môi trường như ở máy (`http://127.0.0.1:8317/v1`, khoá cục bộ `proxypal-local`, id model như
  `gemini-3.8-flash-high`, `claude-opus-5-5`), nên không đổi mã agent. Proxy chỉ nghe localhost và chỉ
  gọi ra nhà cung cấp.
- **Credential đi bằng một dataset private riêng cho lượt chạy**, tạo ở account chạy shard, **xoá sau
  khi thu kết quả** (và quét xoá dataset sót lại khi `status` hoặc lần chạy sau thấy). Không bao giờ
  public (có test khẳng định `public=False`). Nguồn là volume `vipharmind_cli_proxy_auth` hoặc một thư mục
  ngoài repo; file credential **không bao giờ** vào `data/`, git, archive của `data push` hay log (test
  khẳng định `list_archive_files` và log không chứa chúng; log che nội dung).
- **Chỉ đi khi người dùng bật rõ từng lần chạy:** cờ `--with-proxy-credentials` (mặc định tắt), lệnh in
  ra tên file và loại (`antigravity`, `claude`, `codex`) sẽ được tải lên và chỉ tải đúng những file cần
  cho các model của run (`--proxy-credential FILE` để chọn).
- **Giới hạn tốc độ theo nhà cung cấp:** các gói thuê bao có hạn mức, mà shard song song nhân số request.
  Có trần độ song song riêng cho từng nhà cung cấp (Claude thấp nhất) và backoff khi proxy trả
  `quota-exceeded`/`auth_unavailable`; run bị gián đoạn vẫn nối lại được vì trạng thái ở máy.
- **Làm tươi token:** kernel dùng *bản sao* credential; token làm tươi trong kernel không chép ngược về.
  Nếu nhà cung cấp xoay vòng refresh token, bản sao có thể làm bản cục bộ hết hiệu lực: kiểm bằng một job
  ngắn trước khi chạy thật, và giữ bản sao lưu volume.
- **Độ trễ** của model thương mại đo từ datacenter của Kaggle, không phải từ Việt Nam; bài ghi rõ và chỉ
  so giữa các kiến trúc trên cùng một model (spec v2 §2.5).
- **Decision model Jev** (OpenRouter) khác proxy: cần khoá API riêng, người dùng cung cấp sau. Thiết kế
  chừa chỗ: `kernel_env` nhận bản đồ vai trò → điểm cuối. Trước khi có khoá, nếu môi trường local khai
  báo vai `systemone`, lệnh dừng với thông báo rõ thay vì chạy âm thầm với model khác.
- Chạy ở máy (`--backend local`) vẫn dùng được cho model qua proxy, cùng bộ lập kế hoạch và `status`.

(Proxy round-robin của bố cục B ở §4.2 là thứ khác: chỉ nằm trong kernel, nghe `127.0.0.1`.)

### 4.9 Lớp điều phối chung cho mọi bước Kaggle

Tách phần dùng chung ra khỏi từng bước để mọi bước có cùng hành vi: dừng và nối lại, đổi account,
chia shard song song, `status`.

- **Lớp chung** (module do builder đặt tên): lập danh sách account được phép và quota, giữ khoá theo
  account, chạy thread pool các shard, ghi `jobs.json` toàn cục, nối lại kernel đang chạy, backoff khi
  Kaggle trả 429, in bảng quota và giờ reset. Dùng lại `sessions.py`, `quota.py`, `KernelReconciler`.
- **Bộ chuyển đổi cho mỗi bước** cung cấp ba việc: (1) liệt kê đơn vị việc còn thiếu từ kho cục bộ
  (embed: văn bản hoặc truy vấn chưa có trong cache; rerank: cặp (truy vấn, đoạn) chưa có điểm; e2e: cặp
  (cấu hình, câu)); (2) dựng đầu vào cho một lát đơn vị việc; (3) gộp artifact về kho cục bộ,
  idempotent. Tất cả bước đã có (1) và (3) dưới dạng cache; phần mới là chia lát và chạy song song.
- **Lệnh nhận cùng cờ**: `--kaggle-account auto|acc1,acc3` (mặc định `auto`, không còn gắn một account),
  `--parallel N`, `--budget-seconds`, `--max-sessions`; thêm `pharma-lab kaggle status` liệt kê mọi kernel
  đang chạy và quota của mọi account, và `e2e status` / `rerank --status` cho từng bước.
- Thứ tự áp dụng theo lợi ích: rerank (tiêu nhiều giờ GPU nhất và đã có hạ tầng) và e2e (chưa có resume),
  rồi embed corpus và embed truy vấn. Lượt đo profile giữ nguyên.
- Dữ liệu và định danh cache của từng bước **không đổi**, nên không phải làm lại gì đã có.

## 5. Dọn tư duy tunnel (một lượt, cùng lần sửa)

- `2026-10-14-paper-v2-design.md`: viết lại §2.1b (đường gọi model), §2.5 (độ trễ đo trong kernel ở
  concurrency 1 trên một shard duy nhất, không còn "mạng tới tunnel"), bảng A và đoạn C nhắc "tự host
  Kaggle", pha 0 trong §7, các rủi ro §8 nhắc tunnel và `llm-server`; §3 nhắc "năm embedding tự host".
- Các plan `2026-10-16-paper-v2-phase-0/1/2`, `2026-10-20-kaggle-batch-e2e`, spec
  `2026-10-20-kaggle-batch-e2e-design.md`: cập nhật các bước còn nhắc `llm-server`, `rerank-server`,
  `embed-server`. Plan và spec của camera-ready là lịch sử, chỉ thêm ghi chú đầu trang.
- `pharma-lab/docs/guides/e2e-evaluation.md`, `cli-reference.md`, `workflow-local-kaggle.md`: mô tả
  quy trình mới (lệnh, `status`, dừng và nối lại, đổi account).
- `evaluation.md`, `workflow-local-kaggle.md` (embed corpus, embed truy vấn, rerank): cùng cờ mới và cách dừng, nối lại, đổi account.
- Memory: ghi quyết định này.

## 6. Ngoài phạm vi

Tunnel, mở cổng hay phục vụ model ra ngoài kernel; resume *bên trong* một kernel; chia một câu hỏi
giữa nhiều kernel; khoá API trực tiếp (OpenRouter cho Jev, Gemini, Anthropic): người dùng cung cấp sau, thiết kế chỉ chừa chỗ (§4.8). Credential của proxy thì **trong phạm vi**; tự động hoá judge và báo cáo; đổi hạ tầng rerank, embed hiện có;
đụng `camera-ready`, `main`, tag `v1.1.0` hay dataset của bài.

## 7. Kiểm thử và tiêu chí chấp nhận

- Đơn vị: chia shard (cân bằng, tất định, không trùng và không sót cặp); gộp (idempotent, bản `error`
  không đè bản hoàn thành, từ chối danh tính khác); worker (hạn phiên và chụp định kỳ với đồng hồ giả);
  `extract_outputs` vẫn từ chối thành viên lạ; `status`; nhận `--pipeline-option`.
- Giả lập (Kaggle giả như các test của stage hiện có): ba shard song song, giết CLI giữa chừng, chạy
  lại, hoàn tất, không cặp nào chạy thừa hơn một lần thử lại; account hết quota thì chuyển sang account
  khác.
- Thật: một job thử khoảng 20 câu × 2 cấu hình trên một account (khoảng 1 đến 1,5 giờ GPU, cần quota
  sau reset 2026-10-24) để đo thời gian dựng môi trường, VRAM của từng server, và kiểm chứng giả định ở
  §4.3 bằng cách đặt `--budget-seconds` ngắn để ép dừng theo hạn và xem output có về không.
- Mỗi bộ chuyển đổi (rerank, embed corpus, embed truy vấn, e2e) có test: liệt kê đơn vị còn thiếu, chia lát
  không trùng và không sót, gộp idempotent; lớp chung có test với account giả (hết quota thì chuyển account,
  kernel mồ côi không làm sai dữ liệu).
- ruff, pyrefly, `lint-imports` và pytest của `pharma-lab` (và `backend` nếu chạm) đều xanh; code mới
  nằm đúng tầng (`e2e` cho điều phối và worker, `integrations/kaggle` cho phần Kaggle).

## 8. Để builder quyết

Tên và vị trí module mới, định dạng `jobs.json`, thuật toán chia shard cụ thể và các hằng số
(chu kỳ chụp, biên hạn phiên, backoff), cách in `status`, cách đo mốc thời gian dựng môi trường.

## 9. Quyết định

**Của người dùng (đã chốt):** chạy trong kernel, không tunnel; ba mục tiêu: nhanh nhất, dừng và nối
lại dễ, đổi account dễ; sửa toàn bộ trong một lượt.

**Hoãn theo người dùng:** khoá API trực tiếp (Jev qua OpenRouter, Gemini/Anthropic không qua proxy).

**Đã chốt (2026-10-23):** người dùng cho phép đưa **mọi** file credential trong volume proxy lên Kaggle,
gồm cả credential của email công ty `sun-asterisk.com` (Antigravity, Claude, và Codex ghi "enterprise ...
usage-based"). Mình đã nêu rủi ro (quy định của công ty, chi phí theo mức dùng của tổ chức, lộ thì tổ
chức chịu); người dùng vẫn đồng ý. Thiết kế giữ nguyên các biện pháp ở §4.8: cờ bật theo từng lần chạy,
in danh sách file, dataset private xoá sau khi thu kết quả, trần độ song song theo nhà cung cấp.

**Mặc định (đổi được):** lượt đo độ trễ concurrency 1 dùng lát 100 câu `spread` mỗi cấu hình.

**Của mình (có thể đổi):**
- Mỗi account một shard một lúc theo mặc định.
- Không dùng checkpoint dataset phía Kaggle cho e2e.
- Bố cục B (hai bản LLM) để giai đoạn 2, sau khi đo.
- Câu lỗi quá 3 lần thì "kẹt", cần `--retry-stuck` mới chạy lại.
- Chụp định kỳ mặc định 300 giây, tắt được; ngân sách phiên mặc định giữ 3 giờ.
