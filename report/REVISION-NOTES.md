# Ghi chú sửa bài camera-ready (SoICT 2026, paper 1360)

Nguyên văn bốn review: `docs/soict-2026-reviews.md`. Bản đã nộp: tag `v1.0.0`. Số trong Table 2–4 giữ
nguyên như bản đã review; mọi phân tích mới truy được về file trong `pharma-lab/data/evaluation/`.

## Từng điểm review và chỗ sửa

| # | Điểm review | Reviewer | Chỗ sửa trong bài | Bằng chứng |
| --- | --- | --- | --- | --- |
| 1 | Novelty hạn chế, nên định vị là tài nguyên, thiết kế tái lập và đánh giá | R1, R2, R3 | Abstract, Introduction (đoạn contribution: "This is a resource and evaluation paper"), Conclusion | Viết lại câu chữ |
| 2 | Baseline one-step yếu trên câu multi-turn, chưa thử nối lịch sử vào query | R1, R2, R3, R4 | Methodology (baseline Concat RAG), Results e2e, Table 3, Table 4, Fig. 3 | Run `e2e-gemini-cr`, `e2e-qwen35-9b-cr`, config `one-step-history`; câu follow-up: rephrase 0,920 so với Concat 0,750 (Gemini), nugget recall 0,948 so với 0,830 (Qwen); trên toàn tập Gemini Concat kém full agent 0,060 (có ý nghĩa, khoảng nửa khoảng cách của one-step); trên Qwen Concat dưới cả one-step (hallucination 4,0%, faithfulness 0,881) vì query nối lịch sử kéo về đoạn của thuốc ở lượt trước |
| 3 | Lợi thế chủ yếu từ rephrase; judge–refine lợi ít, tốn khoảng 40% token và gần gấp đôi lời gọi | R1, R2 | Results e2e (Table 5 và hai đoạn sau), Discussion | Table 5: mỗi bước trên nhóm câu nó nhắm tới; chia câu theo quyết định đầu của judge (`group_ablation.csv`, `group_type = first_judgement`) |
| 4 | Bỏ reranker không đổi metric e2e | R2 | Results retrieval (slice), Results e2e (Table 5), Discussion | Câu đáp án nằm trong một chunk: 0,771 so với 0,607, p Holm 0,056 (sát ngưỡng); slice sản phẩm cùng thương hiệu 1,4× (`data/evaluation/slices/report.json`) |
| 5 | k = 2 và instruction reranker chọn trên chính benchmark; pilot có tách rời không | R2, R3, R4 | Results retrieval (đoạn dev/test) | Chia dev/test phân tầng, dev chọn lại k = 2 và instruction; test Hit@10 96,1% so với 93,8%; pilot instruction 508 câu dev, 492 câu test, test MRR@30 0,761 lên 0,804 (`data/evaluation/dev-test/report.md`) |
| 6 | Citation recall 0,70–0,72 chưa được phân tích | R2 | Results e2e (đoạn citation) | Gemini full: 25,7% câu không trích dẫn (hơn nửa là tiêu đề, nhãn, câu dẫn), 2,6% trích sai, 96,5% câu có trích dẫn được hỗ trợ (`e2e-gemini/reports/citations.json`) |
| 7 | Safety chỉ 10 câu mỗi loại, không nên tuyên bố mạnh | R1, R2, R3 | Results e2e (đoạn safety), Limitations | Ghi x/10 kèm Wilson CI [0,722; 1,000], bỏ câu "resist all" |
| 8 | Benchmark sinh từ template, enrichment dùng cùng mapping, Hit@30 99,2% có thể quá cao | R1, R2, R3 | Limitations | Câu chữ |
| 9 | Golden và chấm mù chỉ một dược sĩ, thiếu đánh giá lâm sàng độc lập | R1, R3 | Limitations | Câu chữ; không kịp thêm dược sĩ trước 30/10 |

## Thêm ngoài review

- Retrieval: dense và BM25 bổ trợ theo nhóm câu (dense dẫn ở formulary, multi-intent, câu nhiễu;
  BM25 dẫn ở chunk-level và câu kiểu bệnh nhân), hybrid giữ nửa tốt hơn ở năm trên sáu nhóm.
- Bug đọc trích dẫn dạng gộp `[1, 2]` đã sửa trong code chấm; Table 3 giữ số đã công bố, đoạn phân
  tích citation dùng bộ đọc đã sửa.
- Corresponding author (✉) chỉ Quoc-Tuan Nguyen (SoICT chỉ cho một người, người này ký copyright consent); Acknowledgments ghi tài trợ HUST T2025-PC-019.
- Table 5 dòng Guard dùng p Holm 0,014 như các dòng khác (trước ghi p thô 0,002).
- Disclosure of Interests theo hướng dẫn Springer CCIS; copyright consent ký tay nộp riêng (trang camera-ready SoICT).
- Abstract camera-ready chép sang `abstract.txt` để cập nhật EasyChair.
- Giữ Table 1 (thống kê corpus) và Fig. 2 (biểu đồ chi phí); bài vẫn vừa 15 trang.

## Gợi ý cho slide

Câu chuyện ablation: mỗi lớp có tác dụng lớn ở đúng loại câu nó được thiết kế cho, nên trung bình
trên cả tập bị pha loãng.

| Lớp | Loại câu | Bằng chứng |
| --- | --- | --- |
| Truy xuất | Mọi loại | Closed-book so với full: hallucination 18,3% xuống 1,0% (Gemini), 30,6% xuống 1,2% (Qwen) |
| BM25 | Câu có từ hiếm, câu cần đúng chunk | Slice từ hiếm 2,2×; Hit@10 chunk-level 92,0% so với 87,2% của dense |
| Dense | Formulary, câu nhiều ý, câu nhiễu | Hit@10 câu nhiễu 82,6% so với 54,4% của BM25 |
| Reranker | Sản phẩm cùng thương hiệu, đáp án trong một chunk | Slice 1,4×; e2e 0,771 so với 0,607 |
| Rephrase | Câu follow-up | 0,920 so với 0,020 |
| Judge–refine | Câu kiểu bệnh nhân | 1,000 so với 0,657; 61% câu chỉ tốn thêm một lời gọi |
| Guard | Câu không trả lời được, ngoài phạm vi, injection | 10/10 mỗi loại (Gemini), Wilson CI rộng |
