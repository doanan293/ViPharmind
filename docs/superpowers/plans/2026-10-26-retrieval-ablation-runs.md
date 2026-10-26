# Run các ablation retrieval của Phụ lục C (S2, D1, D2, D6 rrf60, D7) và tập judge §3.3

**Trạng thái:** đang chạy (2026-10-26). Plan vận hành: không có mã mới, chỉ chạy lệnh có sẵn và ghi số.

**Goal:** Chốt S2, rồi có đủ số retrieval cho D1, D2, D6 (rrf60), D7 trên golden `9c6e4de6…`, judgments
rules_version 2, cùng embedding và reranker mà §3.4 chọn; dựng tập judge 300 câu của §3.3.

**Spec:** `docs/superpowers/specs/2026-10-14-paper-v2-design.md` §3.4, Phụ lục C.4.

## Quy ước

- Mọi ablation so với **cấu hình đã chọn** (embedding S1, reranker S2), không so với Qwen3-Embedding-4B
  như bản nháp §4.D cũ (D1 "dense Qwen3-Emb-4B", D7 "cùng Qwen3-Embedding-4B"). Lý do: bảng retrieval
  của bài trả lời "mỗi lớp của cấu hình agent đóng góp bao nhiêu".
- Stack đánh giá: `docker compose -p vipharmind-eval` (Postgres 5434, Qdrant 6335); biến môi trường của
  embedding 8B ở `pharma-lab/data/work/eval-env-8b.sh`. Trước khi retrieve, publish release của đúng
  embedding (`pharma-agent corpus publish <release>`; release 8B của bundle `formulary` là `099c331b`).
- Job dài chạy trong tmux, log ở `pharma-lab/data/work/logs-*.log`. Mọi report chạy `metrics --top-k 20`.
- Tên run: `<retriever>-qwen8b-v3-<biến thể>-p50-k20-rrf<k>`.

## Việc

1. **S2 cuối.** `rerank --run hybrid-qwen8b-v3-p50-k20-rrf2 --backend kaggle --model qwen3-reranker:8b-q8_0
   --kaggle-account auto` (20.148 cặp thiếu); `metrics --force`; `metrics select` giai đoạn 2 với bốn reranker
   theo thứ tự chi phí (bge-v2-m3, 0,6B, 4B, 8B); ghi kết quả vào §3.4.
2. **D6, rrf60.** Retrieve `hybrid-qwen8b-v3-p50-k20-rrf60` (`--rrf-k 60`) trên máy; metrics.
3. **D1.** Rerank reranker S2 trên `dense-qwen8b-v3-k20` (Kaggle); metrics; `metrics select --metric hit@5
   --secondary mrr@10` giữa dense + S2 và hybrid + S2 (họ D).
4. **D2.** `bundle embed --bundle data/corpus/formulary-plain --backend kaggle --model qwen3-embedding:8b-q8_0`;
   `pharma-agent corpus import` vào collection `formulary_plain` với alias
   `eval_qwen3_embedding_8b_q8_0_plain`; retrieve `hybrid-qwen8b-v3-plain-p50-k20-rrf2`; rerank S2; metrics.
5. **D7.** Như D2 với `data/corpus/formulary-sections`, collection `formulary_sections`, alias
   `eval_qwen3_embedding_8b_q8_0_sections`, run `hybrid-qwen8b-v3-sections-p50-k20-rrf2`; hai bên chấm
   `--gold-only` (judgments thuộc cách chia mặc định).
6. **Tập judge §3.3** (sau việc 1): `e2e decision-set build --run hybrid-qwen8b-v3-p50-k20-rrf2 --model <S2>
   --size 300`.
7. **Ghi số:** bảng D (theo nhóm và lát) vào `docs/research/paper-v2/08-phase-d-results.md`; bảng tiến độ.

## Ngoài plan này

- D5 (Q0–Q6): chưa có mã cho các chiến lược truy vấn hội thoại; cần plan mã riêng.
- D4: đo tốc độ encode query trên T4 cho năm embedding.
- Bất thường dense Qwen3-Embedding-4B: brute-force cosine trên vector bundle và cache query cho Hit@20
  91,7 % (8B 97,6 %, 0,6B 95,4 %) nên lỗi không ở Qdrant; vector chunk và query cùng file GGUF
  `Qwen/Qwen3-Embedding-4B-GGUF@f4602530` (sha `b60ae5ce…`). Giả thuyết: GGUF không thêm EOS khi
  encode (Qwen3-Embedding lấy token cuối). Kiểm bằng metadata `tokenizer.ggml.add_eos_token` của file
  trên Kaggle và so vài vector với bản transformers chính thức; sai thì embed lại 4B trước khi đưa vào bảng D.
