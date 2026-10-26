# Kết quả pha D: bảng retrieval v2

Ngày 2026-10-26. Golden retrieval `9c6e4de6…` (10.000 câu, 9.970 có gold), judgments rules_version 2
(mọi nhóm). Tập chọn = 8.470 câu (bỏ `conversational` và `safety`); luật chọn §3.4 của spec chạy bằng
`pharma-lab metrics select`. Mọi bảng dưới đây sinh bằng `08-phase-d-tables.py` từ `metrics.jsonl` của
các run trong `pharma-lab/data/evaluation/runs/`; số là phần trăm (nDCG, MRR nhân 100).

## Kết luận

1. **Cặp retrieval của agent: hybrid RRF k=2, prefetch 50, giữ 20, Qwen3-Embedding-4B; rerank
   Qwen3-Reranker-4B, giữ 5.** Ở cả hai giai đoạn bản 8B không hơn bản 4B có ý nghĩa (Hit@20 +0,08,
   Hit@5 +0,30 ở embedding; Hit@5 +0,17, MRR@10 −0,06 ở reranker), nên luật chọn bản rẻ hơn.
2. **Hybrid cần thiết (D1):** sau cùng một reranker, hybrid hơn dense +1,58 điểm Hit@5 (KTC +1,30 đến
   +1,88); lợi nhất ở leaflet và formulary, nơi tên biệt dược và thuật ngữ hiếm cần nửa BM25.
3. **RRF k=2 hơn k=60 (D6, mức retrieval):** +1,83 điểm Hit@5 trước rerank (KTC +1,42 đến +2,24).
4. **Chunk gộp ~1.024 token hơn chunk theo mục (D7):** +2,19 điểm Hit@5 chấm theo mục gold (KTC
   +1,77 đến +2,61), nDCG@5 0,795 so với 0,755.
5. **Enrichment (D2):** đang rerank; trước rerank, bản không enrichment tụt khoảng 7 điểm Hit@5 trên
   9.970 câu.
6. **Hội thoại:** với câu cuối để nguyên (Q0) mọi cấu hình chỉ đạt 21–25 % Hit@5 trên 1.500 câu hội
   thoại; đây là phần D5 (viết lại truy vấn) phải đo, chưa làm.

## Sự cố đo đã sửa

Collection Qdrant của Qwen3-Embedding-4B trong stack đánh giá còn 51.000 point của hai corpus thử
nghiệm cũ. HNSW mặc định với bộ lọc release mất recall (dense 4B Hit@20 90,0 % trên mẫu 400 câu so với
97,2 % khi tìm chính xác) và IDF của BM25 tính trên cả point thừa. Sau khi dọn (mỗi collection chỉ còn
corpus `formulary`), các run `bm25-v3`, `dense-qwen4b-v3`, `hybrid-qwen4b-v3` chạy lại; D2 và D7 chạy
trên stack Postgres và Qdrant tạm riêng. Model 4B không có lỗi: metadata GGUF, vector và cache query
đều khớp.

## Bảng sinh tự động (`phase_d_tables.py`)

### Giai đoạn 1: tìm (chưa rerank), tập chọn 8.470 câu

| Cấu hình | hit@3 | hit@5 | hit@10 | hit@20 | ndcg@5 | mrr@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BM25 | 73.32 | 83.96 | 91.48 | 95.30 | 64.78 | 60.25 |
| dense gemma-300m | 80.58 | 87.33 | 92.11 | 95.02 | 71.64 | 67.93 |
| dense bge-m3 | 88.91 | 92.98 | 95.73 | 97.17 | 81.76 | 78.86 |
| dense qwen 0,6B | 85.97 | 90.73 | 94.11 | 95.89 | 79.00 | 76.36 |
| dense qwen 4B | 90.73 | 94.20 | 96.28 | 97.28 | 84.46 | 81.96 |
| hybrid qwen 4B (rrf2) | 91.50 | 95.81 | 98.18 | 99.09 | 81.20 | 77.17 |
| dense qwen 8B | 90.98 | 94.33 | 96.13 | 97.06 | 85.50 | 83.31 |
| hybrid qwen 8B (rrf2) | 91.78 | 96.10 | 98.32 | 99.17 | 81.94 | 78.04 |

### Giai đoạn 1 trên nhóm hội thoại (1.500 câu, câu cuối để nguyên = Q0)

| Cấu hình | hit@3 | hit@5 | hit@10 | hit@20 | ndcg@5 | mrr@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BM25 | 14.67 | 18.07 | 20.67 | 23.47 | 13.15 | 11.85 |
| dense gemma-300m | 18.53 | 20.93 | 23.27 | 24.47 | 16.14 | 14.86 |
| dense bge-m3 | 20.67 | 22.13 | 24.60 | 25.60 | 18.11 | 17.09 |
| dense qwen 0,6B | 19.60 | 21.40 | 23.53 | 24.93 | 17.85 | 16.94 |
| dense qwen 4B | 19.80 | 22.20 | 23.47 | 24.67 | 18.52 | 17.48 |
| hybrid qwen 4B (rrf2) | 18.87 | 21.13 | 23.60 | 24.60 | 16.85 | 15.74 |
| dense qwen 8B | 20.07 | 22.27 | 23.67 | 25.07 | 18.67 | 17.67 |
| hybrid qwen 8B (rrf2) | 19.13 | 21.47 | 23.53 | 25.27 | 17.25 | 16.10 |

### Giai đoạn 2: rerank trên hybrid qwen 4B, tập chọn

| Cấu hình | hit@3 | hit@5 | hit@10 | hit@20 | ndcg@5 | mrr@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| không rerank | 91.50 | 95.81 | 98.18 | 99.09 | 81.20 | 77.17 |
| bge-reranker-v2-m3 | 94.31 | 96.79 | 98.35 | 99.09 | 89.10 | 87.23 |
| Qwen3-Reranker-0,6B | 95.48 | 97.84 | 98.84 | 99.09 | 89.28 | 86.94 |
| Qwen3-Reranker-4B | 96.73 | 98.22 | 98.87 | 99.09 | 93.11 | 91.90 |
| Qwen3-Reranker-8B | 97.39 | 98.38 | 98.98 | 99.09 | 92.96 | 91.84 |

### D: ablation trên cặp đã chọn (hybrid qwen 4B + Qwen3-Reranker-4B), tập chọn

| Cấu hình | hit@3 | hit@5 | hit@10 | hit@20 | ndcg@5 | mrr@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| cặp đã chọn | 96.73 | 98.22 | 98.87 | 99.09 | 93.11 | 91.90 |
| D1 dense qwen 4B + rerank 4B | 95.34 | 96.64 | 97.07 | 97.28 | 91.93 | 90.88 |
| D2 không enrichment + rerank 4B | chưa có | chưa có | chưa có | chưa có | chưa có | chưa có |
| D6 hybrid RRF k=60 (chưa rerank) | 88.37 | 93.98 | 97.62 | 98.88 | 79.01 | 75.21 |
| hybrid RRF k=2 (chưa rerank) | 91.50 | 95.81 | 98.18 | 99.09 | 81.20 | 77.17 |

Kiểm định (D, hit@5, 8470 câu; KTC bootstrap 95 %, p sign-flip, Holm trong bảng):

| So sánh | Δ (điểm) | KTC 95 % | p Holm |
| --- | ---: | --- | ---: |
| cặp đã chọn − D1 dense | +1.58 | [+1.30; +1.88] | 0.0002 |
| RRF k=2 − RRF k=60 | +1.83 | [+1.42; +2.24] | 0.0002 |

### D7: đơn vị đọc, chấm theo mục gold, cả 9.970 câu

| Cấu hình | hit@3 | hit@5 | hit@10 | hit@20 | ndcg@5 | mrr@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| chunk gộp ~1.024 token | 83.50 | 85.67 | 87.19 | 87.64 | 79.52 | 78.23 |
| một chunk mỗi mục | 80.47 | 83.48 | 86.09 | 86.87 | 75.51 | 74.23 |

Kiểm định (D7, hit@5, 9970 câu; KTC bootstrap 95 %, p sign-flip, Holm trong bảng):

| So sánh | Δ (điểm) | KTC 95 % | p Holm |
| --- | ---: | --- | ---: |
| chunk gộp − chunk theo mục | +2.19 | [+1.77; +2.61] | 0.0001 |

### Theo nhóm và lát, Hit@5

| Nhóm (n) | chọn | không rerank | D1 dense | D2 plain | BM25 |
| --- | ---: | ---: | ---: | ---: | ---: |
| colloquial (343) | 100.00 | 98.25 | 99.42 | — | 94.46 |
| conversational (1500) | 21.73 | 21.13 | 21.60 | — | 18.07 |
| formulary (3444) | 97.71 | 96.84 | 95.70 | — | 83.71 |
| glossary (354) | 99.44 | 97.74 | 98.87 | — | 90.11 |
| leaflet (1721) | 99.13 | 93.61 | 96.75 | — | 85.53 |
| leaflet_short (495) | 100.00 | 98.59 | 97.58 | — | 97.17 |
| multi_hop (300) | 99.00 | 97.33 | 97.67 | — | 92.67 |
| multi_intent (493) | 100.00 | 99.59 | 99.59 | — | 91.28 |
| noisy (492) | 91.26 | 86.38 | 91.46 | — | 51.22 |
| structured (828) | 98.91 | 95.41 | 98.55 | — | 78.74 |
| lát header_dependent (3943) | 96.86 | 93.51 | 95.43 | — | 81.23 |
| lát multi_chunk (751) | 81.76 | 80.69 | 80.69 | — | 75.50 |
| lát name_variant (185) | 92.43 | 85.95 | 92.43 | — | 20.00 |
| lát rare_term (861) | 95.12 | 95.24 | 87.11 | — | 93.96 |
| lát sibling_products (826) | 90.19 | 82.32 | 88.74 | — | 69.73 |
