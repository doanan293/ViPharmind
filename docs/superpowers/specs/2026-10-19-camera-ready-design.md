# Spec: Bản camera-ready SoICT 2026 (paper 1360)

Ngày: 2026-10-19. Trạng thái: chờ duyệt.
Nền: tag `v1.0.0` (`ef81c47`, bản đã nộp), branch `camera-ready`, merge về `dev` rồi `main` khi xong.

## 0. Mục tiêu và ràng buộc

Nộp bản camera-ready của bài "Agentic Retrieval-Augmented Generation for Vietnamese Pharmaceutical
Documents" đã được nhận trình bày oral. Bản cuối trả lời mọi điểm của bốn review mà vẫn là bài đã
được review: cùng corpus, benchmark, golden, model và kết quả, cộng các thí nghiệm bổ sung mà
reviewer yêu cầu. Hướng v2 nằm ở branch `v2.0.0` và không đưa vào bài này.

Ràng buộc:

- Springer CCIS, LNCS, **12 đến 15 trang tính cả references** (trang camera-ready của SoICT). Bản
  v1 build ra đúng 15 trang, nên mọi phần thêm phải được bù bằng cắt.
- Hạn: 30/10/2026 (thư chấp nhận và mục Important Dates). Câu "by October 23, 2026" trong phần
  hướng dẫn trên trang camera-ready được coi là chữ cũ. Mốc nội bộ: xong thí nghiệm trước 25/10 để
  còn thời gian sửa bài.
- Model đúng như v1, dạng F16: Qwen3-Embedding-4B, Qwen3-Reranker-4B có instruction tiếng Việt
  (`-vimed`), Qwen3.5-9B. Setting Gemini dùng đúng model và judge như v1. Vì model trùng nên các
  run v1 có sẵn được dùng lại, không chạy lại.
- Quy tắc của `AGENTS.md`: test đặt trong `tests/`, ruff, pyrefly, lint-imports, không `noqa`, không
  `type: ignore`.

Thành công nghĩa là: mỗi điểm trong §1 có một thí nghiệm hoặc một chỉnh sửa có căn cứ trong bài;
bài build sạch bằng `latexmk` và không quá 15 trang; mọi số mới truy được về file run trong
`pharma-lab/data/evaluation/`; không còn câu nào tuyên bố mạnh hơn số liệu.

## 1. Điểm review và cách trả lời

| Điểm | Reviewer | Cách trả lời |
| --- | --- | --- |
| Baseline one-step yếu trên câu multi-turn; chưa thử nối lịch sử vào query | R1, R2, R3, R4 | Thí nghiệm E1 |
| k = 2 chọn trên benchmark; pilot instruction không rõ có tách khỏi benchmark | R2, R3, R4 | Thí nghiệm E2 |
| Citation recall 0,70 đến 0,72 chưa được phân tích | R2 | Phân tích E3 |
| Novelty của pipeline hạn chế; nên định vị là tài nguyên và đánh giá | R1, R2, R3 | Viết lại contribution (§4) |
| Phần lớn lợi thế đến từ rephrase; judge–refine lợi ít, tốn khoảng 40% token và gần gấp đôi lời gọi; bỏ reranker không đổi metric e2e | R1, R2 | Viết lại Discussion từ số có sẵn (§4) |
| Safety chỉ 10 câu mỗi loại | R1, R2, R3 | Hạ tuyên bố, nêu CI (§4) |
| Benchmark sinh từ template, enrichment dùng cùng mapping; golden và chấm mù chỉ một dược sĩ | R1, R2, R3 | Limitations nêu rõ hơn (§4) |

Pilot instruction đã kiểm: run `hybrid-qwen4b-p50-k30-rrf2-sample1000` lấy 1.000 câu từ chính
benchmark (`sample_seed` 0), không tách rời.

## 2. Thí nghiệm

### E1. Baseline hội thoại `one-step-history`

- Cấu hình: guard, một lần search, answer, như `one-step`; khác ở chỗ query của lần search đầu và
  query của rerank là các câu hỏi trước của người dùng nối với câu hiện tại, cách nhau bằng dấu
  cách. Không gọi LLM để viết lại. `standalone_query` giữ là câu gốc, nên prompt answer giống từng
  byte với `one-step`.
- Dữ liệu: 50 item `multi_turn` của golden v1 (`golden_e2e.jsonl`, sha256 `8bdf0bee…`).
- Setting: Gemini (`e2e-gemini`) và Qwen3.5-9B F16 (`e2e-qwen35-9b`), cùng model theo role, cùng
  retrieval, cùng budget như run v1. Judge `gemini-3.1-flash-lite`, như v1.
- So sánh: ghép cặp với `full` và `one-step` của v1 trên cùng 50 item, sign-flip test, Holm.
  Metric: truthfulness, response rate, nugget recall, hallucination, token và lời gọi mỗi lượt.
- Khối lượng: 100 lượt cộng judge.

### E2. Chọn cấu hình trên dev, báo cáo trên test

- Chia 10.000 câu benchmark thành dev và test 50/50, phân tầng theo nhóm, seed cố định ghi trong
  kết quả.
- Trên dev: chọn k ∈ {2, 60} theo Hit@10 trước rerank (tiêu chí của v1); chọn instruction có hoặc
  không theo MRR@30 của Qwen3-Reranker-0.6B trên phần giao giữa pilot 1.000 câu và dev.
- Trên test: báo Hit@10, MRR@10, nDCG@10 của cấu hình đã chọn, kèm cấu hình còn lại để thấy khoảng
  cách.
- Đầu vào là candidate và rerank score v1 có sẵn; không chạy model.
- Nếu dev chọn khác v1, bài báo đúng kết quả đó và sửa các câu phụ thuộc vào nó.

### E3. Citation recall

- Đầu vào: `judgments.jsonl` và `answers.jsonl` của `full`, cả hai setting.
- Tách các câu văn không được hỗ trợ thành: câu không có trích dẫn; câu có trích dẫn nhưng đoạn được
  trích không hỗ trợ, chia tiếp theo việc claim có được evidence trong prompt hỗ trợ hay không (trích
  sai đoạn so với nội dung ngoài evidence).
- Mẫu tay: khoảng 40 câu không được hỗ trợ, rút ngẫu nhiên có seed, xuất ra file để tác giả gán một
  loại lỗi theo bảng loại cố định (ví dụ câu dẫn dắt hoặc tổng hợp không cần trích, trích sai đoạn
  liền kề, nội dung suy diễn, judge sai). Bảng loại được chốt trong plan trước khi gán.
- Kết quả: phân bố theo từng loại cho mỗi setting.

## 3. Môi trường, code và data

### 3.1 Khôi phục môi trường v1

Code v1 đã có ở tag; phần cần khôi phục là trạng thái chạy, không viết code mới cho nó.

- Data: `pharma-lab/data` hiện là data v2 (37 GB, gitignored). Đổi tên thành `pharma-lab/data.v2`
  (cùng ổ, không sao chép), lấy lại các file được track bằng git, rồi giải nén archive Kaggle
  `doanvanan0209/vipharmind-data` vào `pharma-lab/data`. Archive đã kiểm: sha256 của
  `rag-final/sections.jsonl` và `golden_e2e.jsonl` khớp manifest v1, có đủ run e2e. Xong việc thì
  đổi tên lại.
- Kiểm archive: archive ghi `git_commit` `bc6df6f` và ngày 23/09/2026, sớm hơn tag. Sinh lại
  `e2e report` cho `e2e-gemini` và `e2e-qwen35-9b` từ archive và so với `reports/main.csv` trong
  git v1; lệch thì dừng và báo.
- Postgres và Qdrant: chạy compose của v1 với project name riêng (volume riêng, port riêng). Stack
  của v2 dừng nhưng không xoá. Migrate, import `data/corpus/formulary` với embedding có sẵn trong
  bundle, publish release, trỏ alias như v1.
- Model F16: dựng lại theo `pharma-lab/docs/guides/evaluation.md` và `e2e-evaluation.md` ở tag v1:
  tải từ Hugging Face theo commit ghim, kiểm sha256, chuyển BF16 sang F16 bằng `llama-quantize`, gắn
  instruction `-vimed` cho reranker 4B. sha256 cuối phải khớp catalog. Embedding 4B chạy local
  bằng llama.cpp; reranker 4B và Qwen3.5-9B chạy trên Kaggle như v1.

### 3.2 Thay đổi code

| Chỗ | Thay đổi |
| --- | --- |
| `backend/.../domain/conversation/context.py` | `query_with_history(question, context) -> str` |
| `backend/.../application/chat/context.py` | `PipelineOptions.history_query: bool = False` |
| `backend/.../application/chat/nodes.py` | `search_node` dùng `query_with_history` cho query đầu và rerank khi cờ bật |
| `pharma-lab/.../e2e/configs.py` | `E2EConfig.ONE_STEP_HISTORY = "one-step-history"` |
| `pharma-lab/.../e2e/report.py` | Nhãn "One-step + history" |
| `pharma-lab/.../e2e/harness.py` | `history_query` chỉ ghi vào identity khi `True`, để identity các run v1 không đổi |
| `pharma-lab e2e run` | `--category` để chỉ chạy một nhóm golden |
| `pharma-lab data pull` | `--dataset` để kéo `vipharmind-data`; mặc định giữ nguyên |
| `pharma-lab/.../evaluation/` | Module E2 và lệnh CLI |
| `pharma-lab/.../e2e/` | Module E3: tách loại, xuất mẫu, tóm tắt nhãn tay; lệnh CLI |

Mỗi thay đổi có test viết trước. Docs trong `pharma-lab/docs/guides/` cập nhật cho config và lệnh mới.

Kết quả ghi vào `data/evaluation/e2e/runs/<run>/one-step-history/`, cùng định dạng run v1; E2 và E3
ghi vào thư mục report của run tương ứng. File nhỏ (manifest, report, CSV) được commit như v1.

## 4. Sửa bài

| Phần | Sửa |
| --- | --- |
| Abstract, Introduction, Conclusion | Đóng góp chính là corpus và benchmark, thiết kế tái lập được cho LLM rẻ, và đánh giá đầy đủ; nói rõ các thành phần là kỹ thuật đã có. Bỏ câu hàm ý kiến trúc mới. Kết luận phản ánh E1 |
| Methodology | Mô tả `one-step-history`; nói rõ pilot lấy từ benchmark và cách chọn lại trên dev |
| Results, retrieval | Kết quả E2 |
| Results, e2e | Bảng nhỏ mới cho 50 câu multi-turn: `full`, `one-step`, `one-step-history` × hai setting × truthfulness, response rate, lời gọi mỗi lượt (bảng ablation hiện chỉ có Gemini nên không thêm vào đó); kết quả E3; safety ghi x/10 kèm Wilson CI, bỏ "resist all" |
| Discussion | Rephrase đóng góp phần lớn trên câu follow-up, E1 cho thấy cách rẻ lấy lại được bao nhiêu; judge–refine lợi ít so với chi phí, đề xuất refine có điều kiện; reranker giúp retrieval nhưng không đổi metric e2e |
| Limitations | Benchmark template và enrichment dùng cùng mapping nên Hit@30 có thể cao hơn thực tế; golden do tác giả đầu cùng một dược sĩ soạn, chấm mù chỉ một dược sĩ; safety chỉ là kiểm tra tối thiểu |

Ngân sách trang: phần thêm ước 0,5 đến 0,7 trang. Cắt theo thứ tự: rút gọn Methodology (định nghĩa
metric, công thức PPI đã có nguồn), Related Work, bảng corpus; Discussion viết lại chặt hơn. Không
bỏ trích dẫn, không cắt bảng retrieval.

Hành chính: đánh dấu corresponding author bằng ký hiệu phong bì; permission statement nếu template
CCIS yêu cầu; ZIP gồm thư mục `Source`, file text corresponding author và form đã ký tay (tác giả
ký); sửa tên hoặc email trên EasyChair trước khi ký. `report/REVISION-NOTES.md` ghi từng điểm review
và chỗ sửa.

## 5. Thứ tự

1. Khôi phục data và kiểm archive; dựng lại model F16 (chạy nền, lâu nhất).
2. Song song: E2, E3, code `one-step-history` cùng test.
3. Dựng stack v1, chạy E1 và judge, sinh report.
4. Sửa bài, cân trang, build, chuẩn bị hồ sơ nộp.

## 6. Rủi ro

- Model F16 không dựng lại được đúng sha256: dừng E1 và báo; không thay bằng Q8 khi chưa được đồng ý.
- E1 chưa xong trước mốc 25/10: bài vẫn có E2, E3 và mọi chỉnh sửa câu chữ; Conclusion ghi E1 là
  hạn chế như bản v1.
- Archive không khớp số trong bài: dừng, không dùng archive cho so sánh ghép cặp.
- Kaggle hết quota GPU: dùng các account khác như v1 (`--kaggle-account auto`).
