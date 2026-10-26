# D5: chiến lược truy vấn cho câu hỏi hội thoại (bản nháp thiết kế)

**Trạng thái:** brainstorm xong phần quyết định (2026-10-26), CHƯA DUYỆT bản viết. Bước tiếp: cho
builder check, người dùng duyệt tài liệu, rồi viết plan bằng superpowers:writing-plans. Spec mẹ: `2026-10-14-paper-v2-design.md` Phụ lục C.4 dòng D5.

## Vì sao

Trên 1.500 câu `conversational` của benchmark, khi retriever nhận câu cuối để nguyên (Q0), mọi cấu hình
chỉ đạt 21–25 % Hit@5 (bảng `docs/research/paper-v2/08-phase-d-results.md`). Agent luôn viết lại câu hỏi
trước khi tìm (bước rephrase), nên bài phải cho thấy viết lại giúp bao nhiêu và tốn bao nhiêu.

## Kết luận bảng nhắm tới (người dùng đồng ý 2026-10-26)

"Với hội thoại nhiều lượt, tìm bằng câu cuối thì gần như mù (~22 % Hit@5); chỉ một lượt viết lại bằng
LLM rẻ (đúng bước rephrase hiện có) kéo Hit@5 lên sát mức trần (oracle), còn cách viết lại đắt kiểu
CHIQ (5–6 lượt gọi) không hơn đáng kể mà tốn gấp nhiều lần." Đây là giả thuyết; số đo quyết định.

## Các dòng của bảng (người dùng đồng ý)

Mức retrieval, 1.500 câu conversational, cùng cặp agent: hybrid RRF k=2, prefetch 50, giữ 20,
Qwen3-Embedding-4B, rerank Qwen3-Reranker-4B giữ 5.

| Mã | Truy vấn đưa vào retriever | Lượt gọi LLM |
| --- | --- | --- |
| Q0 | câu cuối để nguyên | 0 |
| Q1 | ghép cả lịch sử hội thoại (câu hỏi và câu trả lời) | 0 |
| Q2-gemini | viết lại thành câu độc lập bằng gemini-3.1-flash-lite, đúng prompt rephrase của backend | 1 |
| Q2-qwen | như trên bằng Qwen3.5-9B | 1 |
| Q3-gemini | CHIQ đầy đủ (làm rõ câu hỏi, mở rộng câu trả lời trước, câu trả lời giả định, nhận biết đổi chủ đề, tóm tắt lịch sử) rồi viết lại | 5–6 |
| Q5 | hợp danh sách ứng viên của Q0 và Q2-gemini bằng RRF trước rerank | 1 |
| Q6 | oracle: câu gốc một lượt của benchmark (`parent_query_id`) | 0 |

Bỏ: Q1b, Q3a, Q3b, Q4 (biến thể, không thêm kết luận). Định nghĩa đầy đủ các chiến lược:
`docs/research/paper-v2/04-advisor-papers.md` mục bảng Q0–Q6.

Cột: Hit@5, nDCG@5 (sau rerank), KTC bootstrap và p sign-flip sau Holm (so với Q0 và so với Q2-gemini,
mỗi so sánh một họ), số lượt gọi LLM, token và giây mỗi lần viết lại. Bảng phụ: Hit@5 theo 8 hiện tượng
(`query_form`: pronoun, ellipsis, intent_shift, drug_shift, answer_entity, topic_switch, multi_intent,
noisy_followup).

## Cách dựng (lựa chọn của Claude, người dùng chưa phản đối)

- Mỗi chiến lược sinh một file evaluation biến thể: giữ 1.500 dòng conversational và gold, chỉ thay
  trường `query`. Sau đó chạy chuỗi có sẵn: `embed queries` (embedding 4B trên CPU ở máy, service
  `llama-embedding` của `compose.local-models.yaml`), `retrieve` trên stack đánh giá sạch, `rerank` 4B
  trên Kaggle, `metrics`.
- Q2 gọi đúng `REPHRASE_SYSTEM` và `rephrase_messages` của backend
  (`backend/src/pharma_agent/domain/agent/prompts.py`) để khớp pipeline thật.
- Q3: prompt CHIQ tiếng Việt mới trong pharma-lab.
- Q5: bước mới hợp hai artifact candidates bằng RRF thành một run, rồi rerank.
- So sánh: `metrics select` hiện từ chối report thuộc file evaluation khác nhau; thêm trường hợp các file
  chỉ khác nhau ở `query` (gold và `query_id` phải trùng).
- Ghi lượt gọi, token, giây mỗi lần viết lại từ usage của LLM.
- Judgments: dựng cho từng file biến thể (`evaluation judgments --evaluation <file>`), cùng luật.

## Quyết định của người dùng (2026-10-26)

1. Rewriter Qwen3.5-9B của Q2-qwen chạy trên Kaggle như mọi run Qwen khác, không qua OpenRouter
   (OpenRouter chỉ dùng cho Jev). Vì vậy Q2-qwen chờ quota sau 2026-10-31 và xếp vào hàng đợi quota.

Không còn quyết định nào mở; bước tiếp theo là builder check rồi plan.

## Ngoài phạm vi

- Đo e2e của các chiến lược (e2e đã có E1 `no-rephrase` trên golden).
- Huấn luyện rewriter (CHIQ-FT).
