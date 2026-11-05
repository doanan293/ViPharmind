# Tập dượt: SoICT 2026, paper 1360 (15 phút gồm Q&A)

Mục tiêu: nói khoảng 11:30, để lại khoảng 3:30 cho Q&A. Speaker notes tiếng Anh nằm trong file PPTX, tổng khoảng 1.570 từ, tương đương 11–12 phút nếu nói khoảng 130 từ/phút.

| # | Slide | Thời lượng | Mốc cộng dồn |
|---|---|---|---|
| 1 | Title | 0:15 | 0:15 |
| 2 | A real question, a real risk (Metformin khi cho con bú: Gemini closed-book "an toàn" ✗ / agent ✓) | 0:55 | 1:10 |
| 3 | Contributions | 0:35 | 1:45 |
| 4 | Corpus (Dược thư + tờ HDSD) | 0:35 | 2:20 |
| 5 | Search the way patients talk (Panadol đỏ, chữ Y, chữ P, TKTW) | 0:55 | 3:15 |
| 6 | Two evaluation sets | 0:40 | 3:55 |
| 7 | Pipeline | 1:05 | 5:00 |
| 8 | Retrieval: bảng 14 phương pháp, 97,5% / 99,2% | 0:45 | 5:45 |
| 9 | Self-hosted embedding ≥ OpenAI; RRF k = 60 vs k = 2 | 0:50 | 6:35 |
| 10 | Reranker 4B là điểm cân bằng; BM25 ×2,2, reranker ×1,4 | 0:50 | 7:25 |
| 11 | Grounding 18× / 25× | 0:45 | 8:10 |
| 12 | Một model mở 9B chạy mọi bước (so sánh từng metric với Gemini) | 0:40 | 8:50 |
| 13 | Averages hide what each step does | 0:50 | 9:40 |
| 14 | What the extra LLM calls buy (Concat RAG, vòng judge–refine 295/185) | 0:45 | 10:25 |
| 15 | Judge + citations | 0:35 | 11:00 |
| 16 | Takeaways (QR + contact) | 0:25 | 11:25 |
| 17 | Thank you · Questions? (để slide này trên màn hình suốt Q&A) | 0:05 | 11:30 |

Nếu bị cắt giờ: slide 12 và 15 mỗi slide chỉ nói một câu, slide 10 bỏ dải "each part pays off".

## Slide backup để mở khi Q&A

- **19**: limitations đầy đủ (template questions, một dược sĩ, Wilson interval [0.722, 1.000]).
- **20**: bảng retrieval đầy đủ, có thêm Hit@3, MRR@30, CER@10.
- **21**: bảng end-to-end đầy đủ (Table 3).
- **22**: ablation, paired change (Table 4).
- **23**: nugget recall theo loại câu hỏi (Fig. 3).
- **24**: lát cắt retrieval và định nghĩa metric.
- **25**: transcript mẫu (follow-up, unanswerable, injection).

## Trước buổi trình bày

- Máy trình chiếu phải có font **Poppins** và **IBM Plex Mono**, đã kèm trong `presentation/fonts/`. Không có font thì PowerPoint sẽ thay font khác và chữ có thể bị lệch.
- Nếu máy không cài được font, dùng `SoICT2026_ViPharmInd_talk_backup.pdf`. Bản PDF render đúng thiết kế nhưng không có speaker notes.
