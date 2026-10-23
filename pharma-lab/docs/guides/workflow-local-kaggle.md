# Local + Kaggle workflow

Build, import, retrieve và metrics chạy ở local; Kaggle chạy embedding (bundle và query) và reranker.

## 1. Kiểm tra môi trường

Khai báo profile Kaggle trong `pharma-lab/.env`:

```dotenv
KAGGLE_ACCOUNT_DEFAULT=acc1
KAGGLE_SHARED_OWNER=account_goc
KAGGLE_ACC1_USERNAME=account_goc
KAGGLE_ACC1_API_TOKEN=token_acc1
KAGGLE_ACC2_USERNAME=account_phu_2
KAGGLE_ACC2_API_TOKEN=token_acc2
```

```bash
uv sync --directory ..    # ở repo root: một .venv chung cho uv workspace
uv run pharma-lab doctor --backend kaggle --kaggle-account acc1
docker compose -f ../compose.yaml -f ../compose.local-models.yaml up -d postgres qdrant llama-embedding
```

Production stage ở profile mode tự tìm checkpoint tương thích trong mọi profile `accN` và mirror sang owner đích trước khi submit kernel.

Chỉ dataset của `KAGGLE_SHARED_OWNER` mà mọi tài khoản cần mount là công khai: bản build llama.cpp `vector-cache-llama-cpp-cuda-t4` và model `vector-cache-gguf-*`, vốn là trọng số open-weight. Input và checkpoint luôn riêng tư.

## 2. Build, validate và export bundle

```bash
uv run pharma-lab build
uv run pharma-lab validate
uv run pharma-lab bundle export --output data/corpus/formulary --force
```

## 3. Embed bundle trên Kaggle

```bash
uv run pharma-lab bundle embed --bundle data/corpus/formulary --backend kaggle \
  --model qwen3-embedding:4b-q8_0 --kaggle-account auto --dry-run
uv run pharma-lab bundle embed --bundle data/corpus/formulary --backend kaggle \
  --model qwen3-embedding:4b-q8_0 --kaggle-account auto --parallel 4
```

Lệnh stream log kernel, tải artifact về và merge vào `data/cache/text_embeddings/qwen3_embedding_4b_q8_0.jsonl`. Exit code 3 nghĩa là kernel chưa xong hoặc hết budget: chạy lại đúng lệnh để resume từ checkpoint. Khi cache đủ, lệnh ghi `embeddings/qwen3_embedding_4b_q8_0.jsonl` vào bundle. `Ctrl-C` chỉ dừng theo dõi; kernel vẫn chạy và lần chạy sau tự attach.

## 4. Import vào backend

```bash
cd ../backend
uv run pharma-agent migrate
uv run pharma-agent corpus import ../pharma-lab/data/corpus/formulary --collection formulary --publish
uv run pharma-agent corpus releases --collection formulary
cd ../pharma-lab
```

## 5. Evaluation dataset và retrieval

```bash
uv run pharma-lab evaluation build --bundle data/corpus/formulary
uv run pharma-lab embed queries --backend kaggle --model qwen3-embedding:4b-q8_0 --kaggle-account acc1
uv run pharma-lab retrieve --run backend-bm25-k30 --retriever bm25 --candidate-k 30
uv run pharma-lab retrieve --run backend-hybrid-qwen4b-p50-k30-rrf2 --retriever hybrid \
  --prefetch-k 50 --candidate-k 30 --rrf-k 2
uv run pharma-lab metrics --run backend-hybrid-qwen4b-p50-k30-rrf2 --top-k 30
```

Thêm `--limit 50` và tên run `...-smoke50` để chạy thử trước.

## 6. Rerank trên Kaggle và metrics

Một model có thể cần nhiều phiên GPU, nên mỗi model chạy trong một cửa sổ tmux riêng; tắt terminal hay mất kết nối chỉ dừng việc theo dõi, các kernel vẫn chạy và lần sau lệnh nối vào:

```bash
tmux new-session -s rerank -n qwen3-reranker-4b
uv run pharma-lab rerank --run backend-hybrid-qwen4b-p50-k30-rrf2 --backend kaggle \
  --model qwen3-reranker:4b-q8_0 --kaggle-account auto --dry-run
uv run pharma-lab rerank --run backend-hybrid-qwen4b-p50-k30-rrf2 --backend kaggle \
  --model qwen3-reranker:4b-q8_0 --kaggle-account auto
uv run pharma-lab metrics --run backend-hybrid-qwen4b-p50-k30-rrf2 --model qwen3-reranker:4b-q8_0 --top-k 30
```

Với `--kaggle-account auto`, mỗi shard (một nhóm truy vấn, một kernel) được giao cho account:

- còn nhiều giờ GPU nhất sau khi trừ phần các kernel đang chạy đã giữ (đọc `kaggle quota -v` của từng profile `accN`), bằng nhau thì `accN` nhỏ hơn;
- không bị lệnh khác khoá (`data/work/locks/kaggle-accounts/<accN>.lock`; mỗi account có hai khoá cho hai phiên GPU cùng lúc);
- còn ít nhất 1 giờ sau phần dự phòng 0,5 giờ; ngân sách phiên = min(`--budget-seconds`, giờ còn lại − 0,5 giờ).

Điểm của mọi shard, kể cả khi kernel dừng giữa chừng, được gộp vào `data/cache/rerank_scores/<model>.jsonl` ngay khi về; cache ở máy là nguồn duy nhất của phần còn thiếu, nên đổi account hay chạy lại không mất điểm. Lệnh chạy tới khi đủ cặp hoặc hết quota; `--max-runs N` giới hạn số kernel, `--parallel N` số shard cùng lúc, `--drain` để các kernel đang chạy xong rồi dừng. `--kaggle-account accN` chỉ dùng một account, `acc1,acc3` dùng đúng các account đó. Dataset model chưa có được tạo công khai bằng profile của `KAGGLE_SHARED_OWNER` (acc1), vì vậy `.env` phải có profile đó; mọi account mount chung model và bản build llama.cpp. Dataset input (câu hỏi đánh giá, text corpus) là riêng tư của account chạy kernel: khi shard chuyển sang account khác, account đó tự upload bản input của mình.

Nhiều model chạy song song, mỗi model một cửa sổ tmux (`tmux new-window -n qwen3-reranker-8b`); khoá tài khoản bảo đảm mỗi account chỉ chạy tối đa hai phiên GPU.

Khi không tài khoản nào còn đủ 1 giờ, lệnh dừng với exit code 3, `stop=quota-exhausted`, và in bảng quota:

```text
account  username                  remaining    total  refresh_at                locked
acc1     account_goc                   0.40h   30.00h  2026-09-19T00:00:00       no
acc2     account_phu_2                 0.20h   30.00h  2026-09-19T00:00:00       yes
```

`refresh_at` là lúc Kaggle làm mới quota của tài khoản; `locked=yes` là tài khoản đang chạy phiên của lệnh khác. Chạy lại đúng lệnh sau thời điểm đó để chấm tiếp.

Mỗi lệnh `pharma-lab rerank` ghi thêm vào `data/work/logs/rerank/<model>.log` (ví dụ `qwen3_reranker_4b_q8_0.log`), có timestamp: tài khoản được chọn, quota trước và sau phiên, kernel, số cặp, lỗi và lý do dừng. Log nằm ngoài `/tmp` nên còn sau khi máy khởi động lại. Theo dõi từ cửa sổ khác:

```bash
tail -f data/work/logs/rerank/qwen3_reranker_4b_q8_0.log
```

Kaggle không truy cập Postgres/Qdrant và không tính metrics; rerank chỉ nhận candidate JSONL cùng manifest.

## 7. Nhiều account, dừng và nối lại

Embedding corpus, embedding truy vấn, rerank và `e2e run` dùng chung một cơ chế:

1. Máy là nguồn sự thật. Phần còn thiếu luôn được tính lại từ cache hoặc `answers.jsonl` ở máy; kernel Kaggle chỉ là nơi tính và có thể bỏ đi.
2. Phần thiếu được chia thành shard vừa một phiên, mỗi shard một kernel, giao cho account còn quota (hai phiên GPU cùng lúc mỗi account). Cùng phần thiếu cho cùng shard, nên chạy lại nối vào kernel đang chạy.
3. Mỗi kernel xong (hoặc dừng giữa chừng) thì kết quả được gộp vào máy ngay; kernel xong sớm thì phần còn lại được chia lại.

Điều khiển: `Ctrl-C` dừng lệnh nhưng để kernel chạy; `--drain` chờ các kernel đang chạy rồi dừng; `--max-sessions`/`--max-runs` giới hạn số kernel; `--parallel N` giới hạn số shard cùng lúc; `--kaggle-account auto|accN|acc1,acc3` chọn account. Đổi account giữa chừng là chạy lại lệnh với `--kaggle-account` khác: tiến độ nằm ở máy.

Xem trạng thái mọi bước và mọi account:

```bash
uv run pharma-lab kaggle status
```

Lệnh liệt kê các kernel đang chạy theo bước và account (đọc `jobs.json` của từng bước), bảng quota GPU với giờ reset, và các dataset `pipeline-cred-*` còn sót lại trên account (credential của proxy, xem [E2E evaluation](e2e-evaluation.md)) kèm lệnh xoá. Một account lỗi API chỉ làm dòng của nó ghi `unavailable`, không làm hỏng cả bảng. Với e2e còn có `e2e status --run R --config C...`.

Không có công cụ nào mở cổng ra ngoài trong kernel: mọi thứ nói chuyện qua `127.0.0.1` và chỉ tải về (`tests/integrations/kaggle/test_no_external_exposure.py` giữ điều này).

## Troubleshooting

- Credential/owner lỗi: sửa `.env`, chạy lại `pharma-lab doctor --backend kaggle`.
- `checksum mismatch` hoặc `no mounted file found`: dataset input chưa `READY` hoặc lệch; chạy lại để reconciler publish đúng version.
- `Expected hits from exactly one published release`: chưa import/publish release, hoặc `retrieval.collections` trỏ sai collection.
- `pinned to release`: release hiện hành đổi giữa chừng; dùng tên run mới.
- `Query embedding cache ... is missing`: chạy lại `pharma-lab embed queries --backend kaggle` với đúng file evaluation và model embedding của backend.
- `--top-k` lớn hơn `candidate-k`: retrieve lại với candidate depth đủ lớn.
- `stop=quota-exhausted`: xem bảng quota và chạy lại sau `refresh_at`.
- `stop=stuck`: một shard hai lần liền không thêm gì (kernel lỗi không có output hoặc llama-server không lên sau 3 lần khởi động lại); đọc `data/work/logs/rerank/<model>.log` và `server-*.log` trong output kernel.
- Máy hoặc WSL khởi động lại khi kernel đang chạy: mở lại tmux và chạy lại đúng lệnh; lệnh nối vào kernel đang chạy trên tài khoản đó thay vì nộp kernel mới.
- Kernel đã kết thúc nhưng điểm chưa về máy và lệnh không còn nối được vào nó (ví dụ cấu hình runtime đã đổi nên job identity khác): `uv run pharma-lab rerank --run RUN --backend kaggle --model MODEL --recover-kernel OWNER/SLUG`, rồi chạy lại lệnh rerank thường để chấm phần còn thiếu.

Chi tiết lệnh: [CLI reference](cli-reference.md). Chính sách bàn giao: [Downstream](downstream.md).
