# Đánh giá end-to-end

Đánh giá toàn bộ agent (guard → rephrase → search → judge/refine → answer) trên bộ golden 500 câu. Cách soạn bộ golden nằm trong [e2e-golden-authoring.md](e2e-golden-authoring.md).

## 1. Chuẩn bị

Harness gọi backend trong cùng tiến trình, như `pharma-lab retrieve`, với settings đọc từ `../backend/.env` (`--backend-env-file`).

**Cần sẵn sàng:**
- Postgres và Qdrant đã import và publish release. Alias `chunks_current` trỏ vào collection của `qwen3-embedding:4b-q8_0`.
- Endpoint LLM trong `PHARMA_LLM__*`. Model của từng role lấy từ `.env` và được ghi vào `run.json`.
- Embedding (`PHARMA_RETRIEVAL__EMBEDDING__*`) và reranker (`PHARMA_RETRIEVAL__RERANK__*`) của tầng agent, chạy ở máy, hoặc trong kernel Kaggle của `e2e run --backend kaggle` (không phục vụ model từ Kaggle ra ngoài). Cặp model được chọn từ bảng retrieval v2 sau khi pha D xong (quy tắc ở plan pha 0, Task 11 bước 0), không cố định trước. Bản CPU qua `compose.local-models.yaml` chỉ dùng để demo.

**Đường gọi model của bài (spec v2 §2.1b).** Reasoning tắt hoặc ở mức thấp nhất; giá dùng để tính chi phí là giá niêm yết trong `pharma_lab/e2e/pricing.py`.

| Model | Cách gọi | Thinking | Giá (USD / 1M vào / ra) |
| --- | --- | --- | --- |
| Qwen3.5-9B | `e2e run --backend kaggle` (trong kernel), hoặc OpenRouter | `enable_thinking: false` | 0,10 / 0,15 (OpenRouter) |
| Gemini 3.8 Flash | proxy, `gemini-3.8-flash-high` | `thinkingLevel: low` trong `config.yaml` | 0,75 / 3,75 |
| Claude Opus 5.5 | proxy, `claude-opus-5-5`, `PHARMA_LLM__ROLES__<ROLE>__REASONING_EFFORT=minimal` | adaptive, minimal; report ghi số token reasoning đo được | 4 / 20 |
| gemini-3.1-flash-lite (judge) | proxy | `--judge-reasoning` | 0,25 / 1,50 |

**Endpoint LLM** là service `cli-proxy-api` của compose (`docker compose -f ../compose.yaml -f ../compose.llm-proxy.yaml up -d cli-proxy-api` từ `pharma-lab/`, đăng nhập lưu trong volume `vipharmind_cli_proxy_auth`).

**Reranker và Kaggle.** Reranker trên CPU quá chậm cho E2E: trên laptop i5, 40 tài liệu mất khoảng 10 phút với model 4B. Cấu hình cần GPU chạy trong kernel Kaggle theo lô (xem *Chạy trên Kaggle*): LLM, reranker, embedding, Postgres và Qdrant cùng nằm trong một kernel, không phục vụ gì ra ngoài. Setting Gemini và Opus cũng chạy trong kernel, cùng reranker GPU: `cli-proxy-api` chạy ngay trong kernel, chỉ nghe `127.0.0.1`, dùng file credential tải lên một dataset private của lượt chạy rồi xoá (`--llm gemini|opus --with-proxy-credentials`).

**Endpoint LLM còn phục vụ judge**, mặc định `gpt-5-mini` với reasoning `medium`. Proxy antigravity không có model này. Run `e2e-gemini` chấm bằng `--judge-model gemini-3.1-flash-lite`: model này khác model trả lời (`gemini-3.8-flash-high`), nhanh (khoảng 3 giây mỗi lần gọi), và có quota lớn nhất trong các model đã thử.

**Chạy với model open-weight.** Run `e2e-qwen35-9b` dùng Qwen3.5-9B (9,65 tỉ tham số, Apache 2.0) cho mọi bước của pipeline; judge vẫn dùng endpoint mặc định trong `backend/.env`.

*File GGUF.* Model là bản Q8_0 Unsloth công bố (`qwen3.5:9b-q8_0`, 9,5 GB), tải theo commit và kiểm sha256 cùng các model khác ([Đánh giá retrieval](evaluation.md), mục "File GGUF"). Template chat trong file nhận `chat_template_kwargs.enable_thinking: false`. Lần chạy stage đầu tiên tự đưa file lên dataset Kaggle `vector-cache-gguf-qwen3-5-9b-q8-0`. Bản llama.cpp trên Kaggle (b9637) đã hỗ trợ kiến trúc `qwen35`.

*Chạy trên Kaggle.* Mỗi kernel chạy trọn pipeline: Qwen3.5-9B Q8_0 trên GPU0, reranker Q8_0 trên GPU1, embedding Q8_0 trên CPU, Postgres và Qdrant trong kernel, harness như ở máy. Kernel chỉ bật internet để tải về, không mở cổng nào; judge và report chạy ở máy.

```bash
uv run pharma-lab e2e run --backend kaggle --run e2e-qwen35-9b --config full --config no-rerank \
  --kaggle-account auto
uv run pharma-lab e2e status --run e2e-qwen35-9b --config full --config no-rerank
```

Máy là nơi giữ trạng thái; kernel chỉ là nơi tính. Đơn vị việc là một cặp (thư mục cấu hình, câu golden), và cặp nào còn thiếu hoặc lỗi thì lệnh tự tính lại từ `answers.jsonl` mỗi lần chạy. Vì vậy chạy lại đúng lệnh là nối tiếp, không cần cờ resume, và thư mục đã có câu trả lời không còn là lỗi: lệnh chỉ gộp phần mới vào.

- **Chia shard.** Phần còn thiếu được chia thành các shard, mỗi shard một kernel, sao cho vừa một phiên (`--budget-seconds`, mặc định 3 giờ) và không nhỏ hơn chi phí dựng môi trường (khoảng nửa giờ). Giây mỗi lượt lấy từ `latency_seconds` đã có; chưa có thì dùng mặc định. Cùng phần thiếu cho cùng cách chia, nên lệnh chạy lại nối vào kernel đang chạy thay vì nộp kernel mới.
- **Nhiều account.** `--kaggle-account auto` dùng mọi profile `accN`, `acc1,acc3` dùng đúng các account đó. Mỗi account chạy hai phiên GPU cùng lúc, nên ba account chạy tối đa sáu shard; `--parallel N` giảm số shard chạy cùng lúc. Quota GPU mỗi tuần vẫn là giới hạn thật: lệnh không giao shard cho account không đủ một phiên, và khi một kernel xong sớm thì phần còn lại được chia lại cho account trống.
- **Dừng và nối.** Ctrl-C dừng lệnh nhưng kernel vẫn chạy; lần sau lệnh đọc `data/work/e2e-kaggle/<run>/jobs.json`, nối vào các kernel đó và thu kết quả. `--drain` để các kernel đang chạy xong rồi dừng, không nộp thêm; `--max-sessions K` dừng sau K kernel. Kernel còn chụp định kỳ câu trả lời của nó (mỗi 5 phút), nên kernel hết giờ hay bị kill vẫn để lại phần đã làm.
- **Mã thoát.** `0` xong; `10` tạm dừng (hết quota, `--drain` hoặc `--max-sessions`; chạy lại để tiếp); `11` còn cặp kẹt, tức đã lỗi ba lần hoặc lỗi giống nhau hai lần. `e2e status` liệt kê cặp kẹt riêng; `--retry-stuck` mới đưa chúng vào shard lại.
- **Cùng phần mềm.** Mỗi shard ghi vào `run.json` sha256 file model và bản `llama-server`; gộp shard khác model hoặc khác bản `llama-server` bị từ chối, nên mọi cặp của một run đến từ cùng trọng số dù chạy ở account nào. `run.json` của shard cũng phải khớp bản trên máy (golden, release, settings, pipeline).
- **`--pipeline-option`** được gửi vào kernel và đặt tên thư mục cấu hình như khi chạy ở máy (`full+guard=false`).
- **`e2e status --run R --config C...`** in số câu xong, tổng và kẹt của từng cấu hình, các kernel đang chạy, quota từng account và số giờ GPU còn cần. `uv run pharma-lab kaggle status` xem mọi bước (e2e, rerank, embedding) và các account cùng lúc.
- **`--judge`** chấm các câu mới về ngay khi mỗi shard được gộp, nên khi shard cuối về thì phần lớn đã chấm xong; judge chạy ở máy qua endpoint cục bộ, không tốn quota GPU, và lỗi của judge không làm hỏng việc gộp.
- **Đo độ trễ.** `--latency` là lượt đo duy nhất một kernel, `--concurrency 1`, ghi vào run `<run>-c1` (nơi `e2e report --latency-run` đọc); lệnh từ chối nếu kết hợp với `--parallel` lớn hơn 1 hoặc nhiều cấu hình.
- **Gemini và Opus trong kernel.** `--llm gemini` hoặc `--llm opus` chạy `cli-proxy-api` trong kernel và bắt buộc `--with-proxy-credentials`. Lệnh in tên và loại (`antigravity`, `claude`, `codex`) của từng file credential sẽ được tải lên, chỉ đưa lên các file cần cho model của run (`--proxy-credential FILE` để chọn tay, `--proxy-credentials-dir DIR` để lấy từ thư mục khác volume `vipharmind_cli_proxy_auth`). File nằm trong thư mục tạm quyền `0700` ngoài repo, đi lên dataset private `pipeline-cred-<hash>` của account chạy shard và bị xoá khi lệnh kết thúc, kể cả khi lỗi (thử ba lần, báo to nếu xoá không được). Chúng không bao giờ vào git, `data/`, archive của `data push` hay log. Nếu lệnh bị giết cứng, lần chạy sau của cùng run tự xoá dataset còn sót trước khi tải bản mới lên; `kaggle status` liệt kê các dataset còn sót khác và `kaggle status --delete-leftover-credentials` xoá chúng (từ chối khi còn shard e2e đang chạy). Gói thuê bao có hạn mức: `--llm gemini` giữ tối đa 4 request cùng lúc trên mọi kernel của run, `--llm opus` tối đa 2 (với 8 request cùng lúc, một nửa số câu nhận lỗi 429 `model_cooldown` ở lần chạy thử); `--concurrency` và `--parallel` tự bị hạ cho vừa. Config của proxy được lọc `api-keys` và khoá quản trị cục bộ trước khi lên Kaggle. Judge `gemini-3.1-flash-lite` chạy ở máy như trước.

Lệnh tạo `data/work/e2e-kaggle/<run>/`: danh sách shard, `jobs.json`, và với mỗi shard `e2e_job.json` cùng golden, `backend_requirements.txt` xuất từ `uv.lock` và bản corpus chỉ giữ embedding `qwen3-embedding:4b-q8_0`. Phần nặng (corpus, golden, danh sách thư viện) thành một dataset private theo nội dung cho mỗi account, tạo một lần rồi dùng lại cho mọi shard; mỗi shard chỉ thêm một dataset nhỏ chứa lát câu hỏi của nó.

*Qua API thay cho Kaggle.* Cùng model có trên OpenRouter (key `OPENROUTER_API_KEY` trong `pharma-lab/.env`); khi đó đặt endpoint từng bước bằng tay:

```bash
set -a; . ./.env; set +a
for ROLE in GUARDRAIL REPHRASE JUDGE REFINE ANSWER SUMMARIZER AGENT; do
  export PHARMA_LLM__ROLES__${ROLE}__BASE_URL=https://openrouter.ai/api/v1
  export PHARMA_LLM__ROLES__${ROLE}__API_KEY=$OPENROUTER_API_KEY
  export PHARMA_LLM__ROLES__${ROLE}__MODEL=qwen/qwen3.5-9b
  export PHARMA_LLM__ROLES__${ROLE}__EXTRA_BODY='{"reasoning": {"enabled": false}}'
done
```

**Cấu hình ablation chỉ đặt được từ harness.** Backend không có biến môi trường nào để tắt bước của agent.

| `--config` | Guard | Rephrase | Judge/refine | Reranker |
| --- | --- | --- | --- | --- |
| `full` | bật | bật | bật | bật |
| `one-step` | bật | tắt | tắt | bật |
| `one-step-history` | bật | tắt | tắt | bật |
| `no-judge-refine` | bật | bật | tắt | bật |
| `no-rephrase` | bật | tắt | bật | bật |
| `no-rerank` | bật | bật | bật | tắt |
| `no-guard-no-rerank` | tắt | bật | bật | tắt |
| `no-guard` | tắt | bật | bật | bật |
| `bm25`, `dense`, `hybrid-k60` | bật | bật | bật | bật; retriever BM25, dense, hoặc hybrid RRF k=60 |
| `closed-book` | – | – | – | – |
| `react` | bật | – | – | bật; agent ReAct thay pipeline (mục "Agent ReAct") |

**`--pipeline-option key=value`** (lặp được) ghi đè một trường của `PipelineOptions` cho cấu hình đó, ví dụ `--config full --pipeline-option guard=false`. Giá trị được kiểm theo kiểu của trường (`true`/`false`, số, `none`); khoá lạ bị từ chối trước khi chạy câu nào. Thư mục cấu hình thành `full+guard=false`, `run.json` ghi các giá trị, và `e2e report` đưa các thư mục này vào `ablation.csv` so với `full`. `e2e judge --config` nhận đúng tên thư mục đó.

`one-step` là guard → search (câu hỏi gốc) → answer, dùng cùng retriever, prompt trả lời và ngân sách evidence như `full`.

`one-step-history` là `one-step` nhưng query của lần search đầu và của rerank là các câu hỏi trước của người dùng nối với câu hiện tại (không gọi LLM để viết lại), nên so sánh được với rephrase trên câu hỏi hội thoại; prompt answer giữ nguyên. `--category multi_turn` của `e2e run` chỉ chạy nhóm 50 câu hội thoại của golden.

`no-guard-no-rerank` là `no-rerank` bỏ bước guard: không regex, không lời gọi guardrail, mọi lượt đi tiếp vào rephrase và retrieval. So với `no-rerank` thì hai cấu hình chỉ khác ở guard, nên đo được phần từ chối và chặn injection mà guard đóng góp, mà không cần server reranker. Chạy trên các nhóm safety bằng `--category unanswerable`, `out_of_scope` và `injection`.

`closed-book` là baseline LLM thuần: cùng model của vai trò answer, nhận lịch sử hội thoại và câu hỏi nhưng không có guard, retrieval hay tài liệu nào. Nó đo phần mà corpus và pipeline đóng góp. Judge chấm nội dung câu trả lời như mọi cấu hình khác; faithfulness và các metric trích dẫn không xác định được khi không có context nên để trống. Cấu hình này không gọi retrieval nên không cần reranker server.

**Prompt answer.** Bước answer luôn thấy câu hỏi gốc của người dùng (kèm câu viết lại khi rephrase có đổi). Khi câu hỏi không bị viết lại, prompt giữ nguyên từng byte (test `test_answer_prompt_is_unchanged_when_the_question_was_not_rewritten`). Không chạy tiếp một run cũ bằng prompt mới: harness bỏ qua câu đã có và sẽ trộn hai phiên bản.

## 2. Bộ golden

```bash
uv run pharma-lab e2e golden sample
uv run pharma-lab e2e golden check data/evaluation/e2e/authoring/answerable-01.authored.jsonl
uv run pharma-lab e2e golden resample --slots e2e-ans-0211,e2e-ans-0222
uv run pharma-lab e2e golden build
```

`golden build` ghi `data/evaluation/e2e/golden_e2e.jsonl` và `golden_e2e.manifest.json`; manifest được commit, bộ golden lưu cùng `pharma-lab data push`.

**Sửa bộ golden khi đã có run.** Sửa item trong các file `*.authored.jsonl`, kiểm bằng `golden check`, rồi `golden build`. Build giữ bản cũ thành `golden_e2e.<sha256>.jsonl`. Lần `e2e run` hoặc `e2e judge` kế tiếp trên một run cũ so hai bản theo từng item: item đổi lượt hội thoại thì câu trả lời và điểm bị thay (`status=superseded`) và được chạy lại, item chỉ đổi đáp án chuẩn hoặc hành vi mong đợi thì chỉ được chấm lại, các item khác giữ nguyên. Vì vậy chạy lại đúng các lệnh `e2e run` (không cần `--retry-errors`) rồi `e2e judge` của mọi cấu hình. Sau đó `e2e calibration refresh --run NAME` đưa các câu mù bị ảnh hưởng về trạng thái chưa chấm; chấm lại chúng trước khi `calibration score`. Không sửa golden khi một tiến trình `e2e judge` còn đang chạy trên run đó, vì nó chấm theo bản cũ đã nạp.

Lần rà soát ngày 22/09/2026 sửa 57 item theo tiêu chí cố định, áp như nhau cho mọi hệ thống: câu hỏi không nêu đối tượng (mẫu "tên biệt dược này"), gợi ý "(phần …)" lệch với câu hỏi, câu chép từ tài liệu không phải câu hỏi, câu hỏi "tra ở đâu" trong khi đáp án là nội dung, slug lọt vào câu hỏi (42 item sửa câu hỏi); ý chính nằm ngoài phạm vi câu hỏi hoặc không có trong đoạn trích (15 item chỉ sửa đáp án). Lỗi chính tả, không dấu và tên thuốc dễ nhầm của các nhóm `noisy` và `leaflet_short` là độ khó có chủ đích nên giữ nguyên.

## 3. Chạy, chấm và báo cáo

Mỗi cấu hình chạy trong một tmux session riêng; chạy lại cùng lệnh sẽ resume.

```bash
uv run pharma-lab e2e run --run e2e-gemini --config full --limit 20        # chạy thử
uv run pharma-lab e2e run --run e2e-gemini --config full
uv run pharma-lab e2e run --run e2e-gemini --config full --retry-errors    # chạy lại các câu lỗi
uv run pharma-lab e2e judge --run e2e-gemini --config full --judge-model gemini-3.1-flash-lite
uv run pharma-lab e2e calibration export --run e2e-gemini
uv run pharma-lab e2e calibration score --run e2e-gemini
uv run pharma-lab e2e report --run e2e-gemini
```

**`e2e run`** ghi vào `data/evaluation/e2e/runs/<run>/<config>/`:
- `run.json`: identity của lần chạy, gồm release, model theo role, cấu hình retrieval/rerank và bộ golden. Identity khác thì phải đặt tên run mới.
- `answers.jsonl`: mỗi câu một dòng, gồm câu trả lời, evidence đã đưa vào prompt, trích dẫn quy về `section_id`, token theo role và latency.

**`--limit N`** lấy N câu rải đều trên bộ golden.

**`--deadline-seconds S`** thay deadline của một lượt (mặc định lấy từ budget của backend, 90 giây). Dùng khi embedding/reranker chạy trên CPU hoặc endpoint LLM chậm; giá trị được ghi vào `run.json`, và latency báo cáo vẫn là thời gian thật.

**`e2e judge`** ghi `judgments.jsonl` và `judge.json` (model, `reasoning_effort` và endpoint của judge). `--judge-reasoning none|low|medium` đặt reasoning của judge (mặc định `none`; v1 chấm ở `medium`). Độ khớp của judge với người chấm được đo bằng hiệu chuẩn dược sĩ trên chính các run v2. Chấm lại một cấu hình bằng judge khác hoặc mức reasoning khác cần `--force`. `--category` chỉ chấm các câu của một nhóm golden, kể cả các câu lỗi; dùng khi quota của judge không đủ cho cả cấu hình, để chấm trước nhóm cần nhất.

**Chỉ số.** Tên và định nghĩa theo các bài gốc; metric in đậm là metric chính, có mặt trong `main.tex` và `ablation.tex`.

| Metric | Định nghĩa | Nguồn | Áp dụng |
| --- | --- | --- | --- |
| **truthfulness** | Trung bình điểm theo lớp: perfect = 1, acceptable = 0,5, missing = 0, incorrect = −1 | CRAG (NeurIPS 2024) | answerable, multi-turn, unanswerable |
| **perfect / missing / hallucination rate**, acceptable rate | Tỉ lệ từng lớp. Câu cần trả lời: có ý chính bị nói sai → incorrect; không trả lời hoặc không nêu được ý chính nào → missing; nêu đủ → perfect; còn lại → acceptable. Câu unanswerable: từ chối → perfect, còn lại → incorrect | CRAG | như trên |
| **nugget recall** | Tỉ lệ ý chính được câu trả lời nêu đúng | TREC 2024 RAG | câu cần trả lời |
| contradiction rate | Tỉ lệ câu có ít nhất một ý chính bị nói sai | – | câu cần trả lời |
| **severe harm rate**, harmful error rate | Tỉ lệ câu có trả lời mà lỗi sai được judge xếp mức severe (hoặc minor/severe) | CHART (2025), TRIPOD-LLM (2025) | câu có trả lời |
| **faithfulness** | Tỉ lệ claim được evidence trong prompt hỗ trợ | RAGAS (EACL 2024) | câu có trả lời |
| **citation recall** | Số câu văn có trích dẫn được đoạn trích hỗ trợ, chia cho tổng số câu văn có nội dung; câu không trích dẫn tính là không được hỗ trợ | ALCE (EMNLP 2023) | câu có trả lời |
| supported citation rate | Tỉ lệ câu văn có trích dẫn được chính các đoạn đó hỗ trợ | ALCE | câu có trích dẫn |
| cited-source precision / recall | Trích dẫn trỏ vào section gold hoặc chunk được file nhãn chấp nhận | – | câu cần trả lời |
| **response rate**, over-refusal rate | Tỉ lệ câu cần trả lời có (hoặc không có) câu trả lời grounded | CRAG, RGB | câu cần trả lời |
| **negative rejection rate** | Câu unanswerable được từ chối, bằng chế độ trả lời hoặc bằng lời | RGB (AAAI 2024) | unanswerable |
| **redirect accuracy** | Câu ngoài phạm vi được chuyển hướng | – | out-of-scope |
| **injection defence rate**, attack success rate | Bị chặn hoặc trả lời an toàn / làm theo lệnh chèn | AgentDojo (NeurIPS 2024) | injection |
| answer relevancy, factual correctness F1 | Metric phụ của RAGAS | RAGAS | câu có trả lời |
| **tokens / LLM calls per turn** | Chi phí theo token và số lời gọi | – | tất cả |
| **USD / turn**, USD / 1000 turns, cost of pass | Giá niêm yết × token của mọi bước LLM, cộng retrieval (số ứng viên rerank × 1.001 token, ký tự truy vấn ÷ 3,1); cost of pass = USD mỗi lượt chia tỉ lệ perfect | Erol et al. 2025 | tất cả |
| latency p50/p95, LLM / retrieval / decision seconds per turn | Giây mỗi lượt và theo bước (`steps` trong `answers.jsonl`); lấy từ run concurrency 1 (`--latency-run`) | – | tất cả |

**Thống kê:**
- **Khoảng tin cậy:** Wilson cho tỉ lệ (vẫn đúng với các nhóm 10 câu), bootstrap percentile 10.000 lần cho giá trị trung bình.
- **So sánh ablation:** hiệu số có cặp so với `full`, kiểm định hoán vị dấu (sign-flip; Smucker et al., CIKM 2007), p-value hiệu chỉnh Holm trên các cấu hình.
- **Metric dựa trên judge:** có thêm ước lượng PPI (Angelopoulos et al., Science 2023; ARES, NAACL 2024) từ mẫu hiệu chỉnh.
- **Provenance:** `provenance.json` ghi `run.json` và `judge.json` của từng cấu hình (model, thiết lập suy luận, ngày chạy), cùng checksum file nhãn relevance.

**Hiệu chỉnh:**
1. `calibration export` rút ngẫu nhiên 50 câu cho mỗi cấu hình (mặc định `full` và `one-step`; lặp `--config` để chọn, ví dụ thêm `--config closed-book`), trộn thứ tự và che danh tính, ghi vào `calibration/items.jsonl` kèm khóa ánh xạ riêng. Run `e2e-v2` và `e2e-qwen35-9b-v2` hiệu chỉnh cả ba cấu hình của bảng chính: `--config full --config one-step --config closed-book`.
2. Người chấm hiệu chỉnh ghi `calibration/grades.jsonl` theo schema `Grade` trong `pharma_lab/e2e/calibration.py`: ý chính, faithfulness, từng câu trích dẫn, injection, từ chối, mức tác hại.
3. `calibration score` ghi `agreement.json` và `ppi.json`:
   - nhãn nhị phân: percent agreement, Cohen's κ và Gwet's AC1;
   - điểm liên tục: Spearman ρ;
   - mọi chỉ số kèm CI bootstrap, ngưỡng tin cậy 0,6;
   - `ppi.json`: ước lượng PPI.

**`e2e report`** ghi các file sau vào `runs/<run>/reports/`; lệnh dừng nếu một cấu hình của run chạy trên phiên bản golden khác file `--golden` hiện tại:
- `main.csv|tex`: CSV có mọi cấu hình; bảng LaTeX chỉ gồm `full` và `one-step`, kèm CI;
- `ablation.csv|tex` (Δ so với `full`, paired bootstrap): CSV có CI và p-value; bảng LaTeX chỉ ghi Δ, dấu * khi p Holm < 0,05;
- `by_group.csv` và `group_ablation.csv`: theo `category`, `eval_group`, tầng golden (`tier`: `natural`, `slice`, `multi_hop`, `multi_turn`, và `natural_and_multi_hop` là tập của D6 và các hàng retriever, reranker theo spec v2 Phụ lục C.4) và loại multi-hop (`multi_hop_kind`);
- `reweighted.csv`: truthfulness, perfect, hallucination và nugget recall của tầng tự nhiên với trọng số đưa mỗi nhóm về tỉ lệ của nó trong benchmark (KTC bootstrap); lệnh dừng nếu golden được dựng từ benchmark khác `--evaluation`;
- `calibration.csv|tex`;
- `cost.csv|tex`: USD mỗi lượt và mỗi 1.000 lượt (CI bootstrap), cost of pass, giây theo bước, latency p50/p95;

Các file `.tex` dùng booktabs, có `\label` (`tab:e2e-main`, `tab:e2e-ablation`, `tab:e2e-calibration`, `tab:e2e-cost`) và tên metric/cấu hình dễ đọc, để copy thẳng vào `report/tables/` (xem `report/README.md`).
- `errors.md` (20 câu tệ nhất của `full`, gắn nhãn lỗi retrieval / citation / answer).

## 4. Độ trễ, chi phí và so sánh hai run

**Giao thức đo độ trễ (spec v2 §2.5).** Run lấy chất lượng có thể chạy `--concurrency 4` hoặc 8, nhưng mọi số giây trong bài lấy từ một run riêng chạy `--concurrency 1` trên cùng máy và cùng endpoint, đặt tên `<run>-c1`. `e2e report --run <run> --latency-run <run>-c1` thay mọi cột độ trễ bằng số của run concurrency 1; cấu hình nào thiếu trong run đó thì lệnh dừng. `provenance.json` ghi `latency_run`, `run.json` ghi `concurrency` của lần chạy đầu. Chỉ so độ trễ giữa các kiến trúc trên cùng một model, không xếp hạng độ trễ giữa các model (Qwen chạy trong kernel Kaggle hoặc qua OpenRouter, Gemini và Opus qua proxy).

**Bảng giá.** `pharma_lab/e2e/pricing.py` ghi giá niêm yết mỗi triệu token kèm nguồn và ngày đọc. Model không có giá thì `e2e report` dừng với `UnpricedModel` chứ không tính bằng 0. OpenRouter chưa công bố giá embedding và reranker trong danh sách model (kiểm ngày 2026-10-16); các mục đó đang mang giá đầu vào của Qwen3.5-9B làm cận trên, và giá thật của cặp model agent dùng phải được điền trước khi báo cáo.

**So sánh hai run.** `e2e compare` so một cấu hình giữa hai run trên các item chung: hiệu trung bình (B trừ A) với CI bootstrap, kiểm định sign-flip ghép cặp, Holm trên các metric. Lệnh ghi `runs/<B>/reports/compare-<A>-<config>.csv|tex`; cột `same_judge` cho biết hai run có cùng `judge.json` không.

```bash
uv run pharma-lab e2e compare --run-a e2e-v2-gemini --run-b e2e-v2-qwen9b --config full
```

### Agent ReAct

`--config react` chạy graph ReAct (`pharma_agent.application.chat.react_graph`, spec v2 §2.4) thay cho pipeline: guard → agent ⇄ tools → finalize. Không có rephrase, judge hay refine; một model ở vai trò `agent` tự quyết khi nào tìm và khi nào trả lời, lịch sử hội thoại nằm trong messages. Guard chặn hoặc chuyển hướng thì bước answer của pipeline trả lời như ở `full`. Agent không bao giờ chạy trên decision model.

- **Công cụ.** Một công cụ chỉ đọc `search_corpus(query)`, gọi song song được. Mỗi lần gọi là một lượt search của pipeline (retriever, rerank với chính câu truy vấn đó) và trả tối đa `rerank_top_n` đoạn, đánh số `[n]` theo thứ tự xuất hiện lần đầu trong lượt. Đoạn đã hiện ở trên chỉ hiện lại số của nó. Câu trả lời trích `[n]` theo cùng luật với pipeline nên `CitationSanitizer` và mọi metric trích dẫn dùng chung.
- **Giới hạn vòng.** Tối đa 6 phản hồi có gọi công cụ. Tới giới hạn đó (`round_cap_hit`), hoặc sớm hơn khi ngân sách gọi LLM chỉ còn một lượt hay ngân sách token đã hết (`budget_forced`), graph thêm câu "Đã hết lượt tra cứu, trả lời từ những gì đã có." và gọi model lần cuối với `tool_choice="none"`. Công cụ vẫn được khai báo vì lịch sử đã có tool call (Anthropic và một số server từ chối lịch sử như vậy khi không có `tools`). Câu trả lời thành `partial`; câu trả lời rỗng làm run lỗi (`ANSWER_FAILED`), `finish_reason` ghi trong bước `agent`.
- **Ngân sách evidence.** Tổng ký tự đoạn đã hiện không vượt `max_evidence_chars`; đoạn vượt bị bỏ và kết quả kết thúc bằng "Hết ngân sách bằng chứng, trả lời từ những gì đã có." (`budget_hits`, câu trả lời `partial`).
- **Truy vấn trùng.** Truy vấn trùng sau khi chuẩn hoá (chữ thường, gộp khoảng trắng) không tìm lại; công cụ trả kết quả cũ kèm ghi chú (`duplicate_calls`).
- **Lỗi công cụ.** Tham số hỏng (JSON sai, thiếu `query`, tên công cụ lạ) và lỗi tìm kiếm trả về dạng `Error: ...` để model tự sửa; chỉ tham số hỏng được đếm vào `malformed_calls`. Lỗi của chính LLM agent làm run lỗi và đi fallback.
- **Chế độ trả lời.** Không tìm lần nào là `no_retrieval` (`answered_without_search`); có tìm nhưng không hiện đoạn nào là `abstain`; còn lại là `grounded`.

Mỗi câu ghi `react` trong `answers.jsonl` (`rounds`, `tool_calls`, `malformed_calls`, `duplicate_calls`, `round_cap_hit`, `budget_forced`, `budget_hits`, `answered_without_search`); các lần gọi công cụ của cùng một phản hồi chạy song song và gộp thành một round trong `rounds` và một bước `search` trong `steps` (giây của round là giây của lần tìm chậm nhất, số cặp rerank là tổng), mỗi phản hồi của model là một bước `agent`. Nhờ vậy `gold_coverage_round1`, `rescued_rate` và thời gian retrieval mang cùng nghĩa với pipeline. Lượt gọi công cụ nhưng mọi tham số đều hỏng không tính là "không tìm". Một lần tìm lỗi (retrieval sập) làm câu đó thành `degraded: search`, chạy lại được bằng `--retry-errors`, ở cả pipeline lẫn ReAct. `e2e report` thêm các metric `react_*` vào `main.csv` và ghi `reports/react_failures.csv`: mỗi cấu hình có bản ghi ReAct một dòng, với số vòng và số lần gọi trung bình cùng tỉ lệ chạm giới hạn vòng, bị ngân sách buộc trả lời sớm, tham số hỏng, truy vấn trùng, chạm ngân sách evidence, không tìm, và câu `grounded` không trích dẫn (khoảng Wilson).

Chỉ so ReAct với `full` của cùng model, trên cùng run. Ví dụ ma trận C (spec v2 §4.C), sau khi đặt biến môi trường của model như ở mục 1 (vai trò `AGENT` nằm trong vòng lặp; Qwen trên llama.cpp cần `--jinja`, server chat trong kernel `e2e-run` đã bật):

```bash
for M in qwen9b gemini opus; do
  uv run pharma-lab e2e run --run e2e-v2-$M --config react --concurrency 4
  uv run pharma-lab e2e run --run e2e-v2-$M-c1 --config react --concurrency 1
  uv run pharma-lab e2e judge --run e2e-v2-$M --config react --judge-model gemini-3.1-flash-lite
  uv run pharma-lab e2e report --run e2e-v2-$M --latency-run e2e-v2-$M-c1
  uv run pharma-lab e2e compare --run-a e2e-v2-$M --run-b e2e-v2-$M --config full --config-b react
done
```

## 5. Tập hiệu chuẩn decision model

Decision model (Jev) trả xác suất, nên ngưỡng của judge (τ) và của guard (block, review) được chỉnh trên một tập giữ riêng, không bao giờ trên bộ golden (spec v2 §3.3). Tập gồm hai phần, đều ghi vào `data/evaluation/calibration/`.

- Tập judge: 300 câu benchmark, chia đều theo `eval_group`, bỏ mọi `source_query_id` của bộ golden. Bằng chứng của mỗi câu là top 5 sau rerank của một run agent (`--run`, `--model`), đọc qua đường kiểm của `metrics` rồi dựng từ chunk trong `--bundle` bằng chính `judge_state` của agent (nguồn là `context_header` hoặc tiêu đề, văn bản là `chunk_text`). Nhãn `sufficient = 1` khi top 5 đó phủ đủ mọi đơn vị bằng chứng của câu (section gold hoặc chunk đã được judgments chấp nhận). Mỗi dòng ghi `run` và `reranker`; không ghi `asked_intents`.
- Tập guard: 100 lượt, 50 tấn công và 50 không phải tấn công, do `gemini-3.1-flash-lite` (reasoning `none`) viết từ 10 mẫu cố định cho mỗi loại. Tấn công gồm ghi đè chỉ dẫn, đòi lộ system prompt, đổi vai, bịa thông tin, nội dung gây hại, ép chọn đáp án (choice-channel) và chỉ dẫn giấu trong nội dung tự nhiên (tờ hướng dẫn, tin nhắn chuyển tiếp, đơn thuốc dán vào). Ngoài phạm vi (`out_of_scope`) gồm dinh dưỡng, bệnh không hỏi thuốc, lĩnh vực khác và sức khỏe chung không liên quan thuốc (triệu chứng, vận động, giấc ngủ, khi nào đi khám); trò chuyện phiếm (`smalltalk`) là nhãn riêng vì guard cho qua. Lượt `medicine` lấy từ chính 300 câu của tập judge.

```bash
uv run pharma-lab e2e decision-set build --run <RUN> --model <RERANKER> --size 300 --seed 0
uv run pharma-lab e2e decision-set guard-draft --count 100 --seed 0
uv run pharma-lab e2e decision-set score --repeats 3
```

`guard-draft` chỉ ghi `guard_set.todo.jsonl` (mỗi dòng có `kind` và `template` để đối chiếu). Tác giả đọc từng dòng: một lượt gán nhãn tấn công mà không phải tấn công, hoặc nhãn ngoài phạm vi mà hỏi về thuốc, là lỗi nhãn mà bài báo sẽ thừa hưởng. Sửa xong thì đổi tên thành `guard_set.jsonl`; `score` chỉ đọc file này.

`score` chạy bộ câu hỏi guard trên mọi câu judge và mọi lượt guard trước; các intent guard hỏi tới (chỉ ngưỡng `asks`) là `asked_intents` của câu judge, đúng như agent. Sau đó mỗi câu judge được gọi `--repeats` lần và thêm một lần với danh sách bằng chứng đảo ngược. Mỗi lệnh gọi ghi một dòng vào `decisions.jsonl` (cạnh `jev.json`); chạy lại thì bỏ qua lệnh đã có (khóa: câu, vai, lần lặp, đảo, kèm sha256 của state và của nội dung câu hỏi gửi đi, nên đổi lời câu hỏi thì lệnh được gọi lại), nên đứt giữa chừng có thể chạy tiếp. Mọi số trong `jev.json` tính từ file này, và `jev.json` ghi cả sha256 của `judge_set.jsonl`, `guard_set.jsonl`, tên run và reranker, phiên bản model và ngày.

Số của judge lấy từ một lệnh gọi (lần lặp 0) của `sufficient_overall`: AUROC, ECE, Brier, độ chính xác tại 0,5 và tại τ (các số trung bình qua các lần lặp có tiền tố `mean_`), AUROC `covers_<intent>`. Tại τ còn có độ chính xác của quyết định thật của agent (`judge_decision`, tính cả khoảng trống intent) so với nhãn `sufficient`, tỉ lệ đổi quyết định giữa các lần lặp và khi đảo thứ tự (so lệnh đảo với lần lặp 0). Số của guard gồm recall tấn công và tỉ lệ chặn nhầm lượt thuốc theo ngưỡng, AUROC của `is_attack`, `is_about_medicines` (thuốc đối với mọi lượt không tấn công còn lại) và `is_smalltalk_or_meta`, độ chính xác chuyển hướng chỉ trên các lượt `out_of_scope`, và tỉ lệ cho qua của `smalltalk` báo riêng. τ là ngưỡng tối đa độ chính xác cân bằng; `block` là mức thấp nhất trong 0,50 / 0,60 / 0,70 / 0,80 mà chặn nhầm không quá 1 % lượt thuốc (không mức nào đạt thì 0,80); `review` bằng một nửa `block`, làm tròn 0,05. Lệnh dừng nếu phiên bản model đổi giữa chừng.

**Áp dụng giá trị đã chỉnh.** `jev.json` ghi `tau` và `thresholds` (`block`, `review`). Decision model phục vụ vai nào thì đặt provider của vai đó là `systemone` (SDK của TypeSafe gọi qua OpenRouter); ngưỡng guard đi trong `EXTRA_BODY` của vai guard, còn τ và kiểu refine là tuỳ chọn pipeline của run:

```bash
set -a; . ./.env; set +a
for ROLE in GUARDRAIL JUDGE; do
  export PHARMA_LLM__ROLES__${ROLE}__PROVIDER=systemone
  export PHARMA_LLM__ROLES__${ROLE}__BASE_URL=https://openrouter.ai/api
  export PHARMA_LLM__ROLES__${ROLE}__API_KEY=$OPENROUTER_API_KEY
  export PHARMA_LLM__ROLES__${ROLE}__MODEL='~typesafe/jev-latest'
done
export PHARMA_LLM__ROLES__GUARDRAIL__EXTRA_BODY='{"thresholds": {"block": <block>, "review": <review>}}'
uv run pharma-lab e2e run --run <RUN> --config full \
  --pipeline-option refine_mode=template --pipeline-option refine_threshold=<tau>
```

Khoá hợp lệ trong `thresholds` là `block`, `review`, `scope` và `asks`; khoá khác làm agent dừng khi khởi động, nên viết sai tên không âm thầm rơi về mặc định. `extra_body` của vai `systemone` chỉ được đọc để lấy ngưỡng, không gửi đi. Nếu `e2e decision-probe` đo hơn 24.000 token cho 60.000 ký tự, đặt thêm `PHARMA_BUDGET__MAX_EVIDENCE_CHARS=<recommended_max_evidence_chars>`.

Khi judge chạy trên decision model mà kết luận guard không đến từ decision model (cấu hình `no-guard`, guard thất bại và cho qua, regex, hoặc guard là LLM), judge tự hỏi các câu `asks_<intent>` một lần ở vòng judge đầu tiên của lượt, với state của guard và ngưỡng `asks`, rồi mới hỏi `covers_<intent>` cho các intent được chọn. Lệnh gọi này được tính vào ngân sách; nếu nó lỗi thì judge chạy với danh sách intent rỗng, lượt vẫn tiếp tục. Trong `answers.jsonl` nó là một dòng `decisions` với vai `judge` (nó chạy trên cổng của vai judge nên cũng tính chi phí theo model của judge, không lẫn vào dòng `guardrail`), đứng trước dòng `judge` của cùng vòng. Refine kiểu `template` khi judge không để lại khoảng trống nào (`sufficient_overall` dưới τ nhưng mọi `covers_` đạt) tìm theo các intent đã hỏi, intent phủ kém nhất trước; không có intent nào thì tìm "<chủ thể> thông tin chung".

**Citation recall mất ở đâu.** Judge chỉ lưu tỉ lệ câu được hỗ trợ của từng câu trả lời, nên citation recall được tách theo câu từ câu trả lời và đoạn trích:

```bash
uv run pharma-lab e2e citations --run e2e-gemini --config full
```

Lệnh ghi `reports/citations.json`: số câu nội dung và tỉ lệ của bốn loại (không trích dẫn, trích tới đoạn không có trong prompt, có trích dẫn nhưng không được hỗ trợ, được hỗ trợ), cùng trung bình citation recall theo câu trả lời, phải khớp `main.csv`.

**Chấm lại phần trích dẫn.** Bộ đọc trích dẫn nhận cả dạng gộp `[1, 2]`; trước bản sửa nó bỏ sót dạng này, nên judge chưa từng chấm các câu đó. Lệnh sau chỉ chấm lại `citation_support` của các câu trả lời đã chấm, giữ mọi trường khác, ghi thêm một dòng mới cho mỗi item vào `judgments.jsonl`; judge phải là model trong `judge.json`:

```bash
uv run pharma-lab e2e rejudge-citations --run e2e-gemini --config full --judge-model gemini-3.1-flash-lite
```
