# Hiệu năng và chất lượng trên máy local

Máy: Intel i5-13420H (12 luồng, AVX2, AVX-VNNI), 21 GB RAM, WSL2, không có GPU NVIDIA. Stack:
`scripts/demo-stack.sh` (LLM Gemini qua CLIProxyAPI, embedding `qwen3-embedding:4b-q8_0` bằng llama.cpp CPU).

## Bộ đo

- Golden e2e: `pharma-lab/data/evaluation/e2e/golden_e2e.jsonl` (schema `e2e-golden-v3`, sha256
  `1dae2820…ba309`, `bundle_manifest_sha256` `8d9315d9…260c` khớp `pharma-lab/data/corpus/formulary/manifest.json`).
- 20 câu: `pharma-lab e2e run --category answerable --limit 20` (lấy rải đều trên nhóm câu trả lời được, tất định):
  `e2e-ans-0041, 0329, 0416, n0031, n0062, n0095, n0126, n0157, n0188, n0220, n0251, n0282, n0314, n0346, n0377,
  n0408, n0439, s0008, s0059, s0098`.
- Judge: `claude-haiku-5-5` qua proxy (`gpt-5-mini` mặc định không có trên proxy; Codex hết quota). Mọi lần so trước và
  sau dùng cùng judge này.

## Rerank trên CPU

Đo trực tiếp `/v1/rerank` của llama.cpp `server-b10920`, `qwen3-reranker-0.6b-q8_0-vimed`, đoạn khoảng 1.700 token:

| Số đoạn | Thời gian |
| --- | --- |
| 5 | 71 s |
| 10 | 121 s |
| 15 | 194 s |

Model embedding 0.6B có cùng tốc độ (khoảng 100 token/giây, 12 luồng, CPU 1.088%), nên đây là giới hạn phần cứng
chứ không phải cấu hình (đổi `-np`, `-c`, flash attention không đổi đáng kể). Rerank 4B chậm hơn nữa (compose ghi p95
449 s mỗi request). Một vòng rerank vượt hạn 90 giây của một lượt.

Quyết định: demo tắt rerank (`DEMO_RERANKER=none`, chỉ hybrid RRF). Căn cứ chất lượng: ablation của bài báo trên 480
câu với Gemini (`runs/e2e-gemini/reports/ablation.csv`): `no-rerank` so với `full` có truthfulness −1,8 điểm phần trăm,
KTC 95% [−5,0; +1,5], p = 0,32 (không có ý nghĩa thống kê).

## Mốc (2026-11-26, cấu hình `no-rerank`, 1 lần chạy)

Run `demo-baseline` (`pharma-lab/data/evaluation/e2e/runs/demo-baseline/`).

| Chỉ số | Giá trị (KTC 95%) |
| --- | --- |
| truthfulness | 0,725 (0,425–0,95) |
| perfect_rate | 0,75 (0,53–0,89) |
| hallucination_rate | 0,10 (0,03–0,30) |
| nugget_recall | 0,865 |
| faithfulness | 0,857 |
| citation_recall | 0,693 |
| độ trễ một lượt p50 / p95 | 23,0 s / 51,3 s |
| thời gian LLM mỗi lượt | 28,2 s (trung bình) |
| lời gọi LLM mỗi lượt | 4,6 |

Tách theo bước (p50 / p95, giây): guard 1,3 / 1,9; search 1,9 / 15,8; answer 19,0 / 43,2; refine (4/20 lượt) 11,0 /
13,8. Điểm nghẽn: bước trả lời (`gemini-3.8-flash-high`, bằng chứng khoảng 16.600 ký tự).

Không tối ưu thêm: chủ dự án (2026-11-26) quyết demo chỉ ngắn, giữ Gemini 3.8 Flash mặc định và tắt rerank ở demo;
thời gian tới chữ đầu tiên không đo.

Lưu ý so sánh: run `demo-baseline` chạy trước bản sửa trích dẫn gộp (`bb7a546`, "[1, 2]" thành "[1], [2]"), nên số
trích dẫn được đếm của nó thấp hơn các run sau; run của paper v2 cũng vậy.
