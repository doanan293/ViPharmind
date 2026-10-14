# Nghiên cứu nền cho bản paper v2

Ghi chú nghiên cứu được thực hiện ngày 2026-10-14, sau khi bản SoICT 2026 được đóng băng ở release
[v1.0.0](https://github.com/doanan293/ViPharmind/releases/tag/v1.0.0). Sáu file dưới đây là tài liệu
gốc cho spec `docs/superpowers/specs/2026-10-14-paper-v2-design.md`. Mỗi mục trong các file ghi rõ
nguồn đã mở và mức xác minh (VERIFIED / PARTIAL / UNVERIFIED hoặc [V] vendor / [I] độc lập / [D] suy ra).

| File | Nội dung | Dùng cho |
| --- | --- | --- |
| `01-deepseek-harness.md` | Vòng lặp `ReactLoopAgent` của DeepSeek Harness (dsh): bước, điều kiện dừng, retry, tool, cắt kết quả, compaction, prompt | Thiết kế baseline ReAct (§2.4 của spec) |
| `02-codex-claude-agent-loop.md` | Vòng lặp của OpenAI Codex (`codex-rs/core`), hướng dẫn của Anthropic (workflow so với agent, tool design, context engineering), Claude Agent SDK | Thiết kế baseline ReAct, định nghĩa workflow/agent cho bài |
| `03-jev-typesafe.md` | API, giới hạn, giá, độ trễ, hiệu chuẩn và rủi ro của TypeSafe Jev; bộ câu hỏi nháp cho guard, judge và grader | Adapter decision model (§2.1), ngưỡng gating (§2.3), limitations |
| `04-advisor-papers.md` | Ba bài thầy gửi (Rewrite-Retrieve-Read, CHIQ, Fensore 2025) đọc toàn văn, số liệu, prompt gốc, hàm ý | Benchmark hội thoại và so sánh chiến lược viết lại (§3.1, §4.D), khung luận điểm Fensore |
| `05-literature-survey.md` | Khảo sát 2023-2026 theo sáu luồng: workflow so với agent, adaptive retrieval và gating, chi phí và độ trễ, guardrail và judge nhỏ, decision model, RAG hội thoại, tiếng Việt; kế hoạch trích dẫn | Related work, định vị đóng góp, limitations |
| `06-repo-map.md` | Bản đồ kỹ thuật backend và pharma-lab: graph, budget, port LLM, cấu hình e2e, identity, latency, báo cáo, và khoảng trống cho từng thí nghiệm | Mọi phần triển khai của spec và plan |

## Kết luận chính rút ra

- **Khoảng trống thật sự.** Chưa có công trình nào đặt một decision model không sinh văn bản vào vòng
  điều khiển RAG làm judge đủ bằng chứng, đo hiệu chuẩn của nó trên miền phi tiếng Anh, gate vòng
  retrieve-more theo xác suất đã hiệu chuẩn rồi quét ngưỡng thành đường Pareto chất lượng, độ trễ, chi
  phí, và so sánh workflow với ReAct khi giữ nguyên task, tool và giao diện gọi trên một dải model nhỏ
  (xem `05-literature-survey.md` §H).
- **Công trình gần nhất phải đối chiếu.** Ferrazzi et al. 2026 (ACL Industry) so sánh pipeline cố định
  với agent trên Qwen3 0.6B đến 32B, agent chỉ thắng ở 0.6B và tốn 1,5 lần thời gian; Kumar et al. 2026
  thấy workflow cố định thắng 12/19 benchmark và rẻ hơn ở 19/19; TASR và HALT 2026 dừng vòng lặp bằng
  logit margin hoặc verifier đã huấn luyện; Tiny-Critic RAG dùng gatekeeper 1,7B có fine-tune; REFLEX
  dùng Jev để escalate model. Bài ta khác ở decision model đã hiệu chuẩn, gate retrieve-more, Pareto
  theo USD và giây, dải model cộng model thương mại, tiếng Việt, nhiều lượt.
- **Decision model.** Jev: `POST /v1/systemone`, noul/choice/score, 64k token mỗi request, 0,042 USD mỗi
  triệu token vào, output miễn phí, ghim `jev-1.13.0`. Benchmark độc lập (arXiv 2609.37647): choice ECE
  0,028 nhưng nhiều noul trong một request thiên về "có" (ECE 0,168), nên ngưỡng phải chỉnh trên tập giữ
  lại và báo AUROC. Jev yếu nhất ở prompt injection (0,741). Đối chứng open weights: Strands Decider 2B
  (Apache-2.0, nền Qwen3.5-2B, cùng API, ECE 0,064 tự báo).
- **Baseline ReAct công bằng.** Cả dsh, Codex và Claude Agent SDK dừng khi phản hồi không còn tool call;
  Codex không có giới hạn bước; dsh cũng không. Baseline của ta thêm giới hạn 6 vòng tool với câu trả
  lời bắt buộc khi hết, chặn gọi trùng, cắt kết quả theo đầu và đuôi, cùng mức bằng chứng và cùng định
  dạng trả lời với pipeline.
- **Ba bài thầy gửi.** Rewrite-Retrieve-Read và CHIQ đánh giá viết lại ở mức retrieval với cùng index, và
  CHIQ cho thấy làm giàu lịch sử thu hẹp khoảng cách model mở với model đóng. Fensore kết luận RAG không
  giúp khi P@5 chỉ 0,15 và kêu gọi retrieval có điều kiện theo độ tin cậy cùng benchmark nhiều lượt, đúng
  hai thứ bài v2 làm.
- **Mã hiện tại.** Port LLM chỉ có `structured` và `stream`, chưa có tool calling; cấu hình e2e là enum
  cố định; latency chỉ có tổng mỗi lượt; chưa có bảng giá; enrichment không có cờ tắt; benchmark retrieval
  chưa có trường `turns`. Bài v1 nói top 5 sau rerank và 30 ứng viên trong khi mã dùng top 8 và 40.
