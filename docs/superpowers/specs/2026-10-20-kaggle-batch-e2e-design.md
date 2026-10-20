# Spec: E2E trên Kaggle chạy trọn trong một kernel, bỏ tunnel

Ngày: 2026-10-20. Trạng thái: chờ duyệt. Nhánh: `camera-ready`.

## Vì sao

Ngày 19/10 Kaggle khóa tài khoản `doanan02092003` vì "Resource abuse": `e2e rerank-server` và
`e2e llm-server` chạy llama-server trong notebook rồi mở tunnel cloudflared để máy local gọi vào.
Quyết định của tác giả (20/10): không còn tunnel công khai nào. Phần nào cần GPU Kaggle thì chạy
mọi thứ trong một kernel theo lô và ghi kết quả ra; phần nào chạy ở máy nhanh hơn thì để ở máy.

## Mục tiêu

1. Xóa toàn bộ đường tunnel: code, lệnh CLI, test, docs.
2. `pharma-lab e2e run --backend kaggle` chạy một cấu hình e2e của setting Qwen trọn trong một
   kernel: Qwen3.5-9B, reranker, embedding, Qdrant, Postgres và harness đều ở trong kernel, không có
   cổng nào mở ra ngoài. Máy local chỉ đẩy job, chờ, tải `answers.jsonl` và `run.json` về đúng thư
   mục run như khi chạy local.
3. Chấm (`e2e judge`) và report vẫn chạy ở máy, qua proxy Gemini, như hiện nay.
4. Việc trước mắt cần nó: guard ablation cho setting Qwen. Một job chạy cả `no-rerank` và
   `no-guard-no-rerank` trên 30 câu safety (`e2e-qwen35-9b-cr`), cùng model và cùng phiên kernel, để
   hai cấu hình chỉ khác nhau ở guard (Qwen chưa có run `no-rerank`).

## Không làm

- Không chạy setting Gemini có reranker trên Kaggle: mỗi lượt cần cả proxy Gemini (chỉ có ở máy)
  lẫn reranker (chỉ có trên GPU), không nối được khi không có tunnel. Setting Gemini vẫn chạy ở máy,
  không reranker hoặc với reranker trên máy. Ghi rõ giới hạn này trong guide.
- Không đổi model, retrieval, prompt hay ngân sách của các run đã có; identity của run cũ không đổi.
- Không thêm đường API trả phí.

## Ràng buộc

- Không kernel nào mở cổng hay tunnel. Kernel được bật internet chỉ để tải về (pip, binary Qdrant,
  gói Postgres); không phục vụ gì ra ngoài.
- Model: `qwen3.5:9b-q8_0` cho mọi role, `qwen3-reranker:4b-q8_0`, `qwen3-embedding:4b-fp16`, sha256
  theo catalog. Q8_0 vì F16 của Qwen cần cả hai T4. Lưu ý: run Qwen `full` và `one-step` của v1 dùng
  F16, run `one-step-history` dùng Q8_0, nên so sánh giữa chúng là khác độ chính xác; guard ablation
  tránh điều này bằng cách chạy cả hai cấu hình trong cùng job.
- Bố cục GPU (quyết định của tôi): GPU0 chạy Qwen Q8_0 (9,5 GB); GPU1 chạy reranker Q8_0 (4,3 GB) và
  embedding F16 (8 GB). Mỗi model một llama-server trên `127.0.0.1` trong kernel.
- Dùng hạ tầng batch sẵn có: stage, dataset model, checkpoint, chọn account theo quota. Không dùng
  `--kaggle-account auto` để chạy job dài trên account có rủi ro; mặc định account trong `.env`.
- Quy tắc `AGENTS.md`: test trước, ruff, pyrefly, không `noqa`, không `type: ignore`.

## Cách làm (phần đã chốt)

1. **Bundle nguồn** gồm cả `backend/src/pharma_agent` cạnh `pharma_lab` (test hiện cấm
   `pharma_agent` trong bundle sẽ đổi cho stage e2e). Phụ thuộc của backend cài bằng pip trong kernel.
2. **Corpus trong kernel:** cài Postgres (apt) và chạy binary Qdrant chính thức trên localhost, rồi
   `pharma-agent migrate` và `pharma-agent corpus import` từ bundle `data/corpus/formulary` kèm
   embeddings có sẵn, publish release, alias `chunks_current` như stack v1. Bundle đi vào kernel
   dưới dạng dataset input.
3. **Model trong kernel:** mở rộng `managed_model_servers` để chạy nhiều model một lúc (hiện chỉ cho
   đúng một `*.gguf`), mỗi model một cổng, đặt GPU theo bố cục trên.
4. **Stage `E2E_RUN`:** cấu hình e2e, danh sách item (hoặc `--category`), golden, các dataset trên.
   Worker đặt biến môi trường trỏ vào các server localhost rồi gọi đúng `run_e2e` của harness, ghi
   `answers.jsonl` theo journal để chạy tiếp được khi hết giờ kernel (cơ chế checkpoint sẵn có).
5. **CLI:** `e2e run --backend kaggle` (mặc định `local`). Kết quả tải về được ghép vào
   `data/evaluation/e2e/runs/<run>/<config>/` như run local; `run.json` ghi đủ model, retrieval và
   `backend=kaggle` chỉ khi chạy trên Kaggle (identity run cũ không đổi).
6. **Xóa tunnel:** `workers/serve.py`, `e2e/model_server.py`, `ModelServeStage`, `RERANK_SERVE`,
   `LLM_SERVE`, lệnh `rerank-server` / `llm-server` / `--attach`, `serve_runtime` trong catalog, các
   test và đoạn docs tương ứng, thư mục `data/work/serve/`.
7. **Docs:** `pharma-lab/docs/guides/e2e-evaluation.md` viết lại phần chạy setting Qwen bằng
   `--backend kaggle`; nêu giới hạn setting Gemini có reranker.

## Quyết định của tôi sau khi rà

- Một job chạy trọn trong một phiên kernel: nạp corpus một lần, mọi cấu hình và nhóm câu của job
  dùng chung một release, nên `release_id` trong identity nhất quán. Job không cần chạy tiếp qua
  nhiều phiên; nếu hết giờ thì chạy lại cả job.
- Kết quả tải về thành thư mục cấu hình mới trong run. Nếu thư mục đó đã có `answers.jsonl`, lệnh từ
  chối, không trộn hai lần chạy. `run.json` do job trong kernel ghi.
- CLI nhận nhiều `--config` và nhiều `--category` trong một job.

## Để người làm tự quyết

- Cách cài Postgres và tải Qdrant trong kernel (apt, binary), miễn là pin phiên bản.
- Cách chia nhỏ job khi 500 câu không xong trong một phiên kernel.
- Chi tiết số slot, context của từng llama-server.

## Kiểm tra xong

- Không còn chuỗi `cloudflared`, `tunnel`, `rerank-server`, `llm-server` trong code và docs đang dùng.
- Test và lint pass.
- Một job thật: `e2e run --backend kaggle --run e2e-qwen35-9b-cr --config no-rerank --config
  no-guard-no-rerank --category injection --category out_of_scope --category unanswerable` chạy
  xong, câu trả lời về đúng hai thư mục và `e2e judge` chấm được ở máy.
