# Review dữ liệu trước khi làm paper v2

Ngày 2026-10-14. Đối tượng: corpus `data/corpus/formulary` (knowledge bundle đang dùng), benchmark
retrieval `data/evaluation/gold/section_retrieval_eval.jsonl` (10.000 câu), file nhãn relevance
`section_retrieval_eval.judgments.jsonl`, bộ golden e2e `data/evaluation/e2e/golden_e2e.jsonl`
(500 item). Mọi số liệu dưới đây đo trực tiếp trên dữ liệu bằng chunker của backend
(`chunk_section`, `MAX_CHUNK_CHARS = 3000`) và tokenizer của Qwen3-Embedding-4B.

## 1. Kết luận ngắn

1. **Không nên tăng độ dài chunk trước khi sửa cấu trúc.** Vấn đề không nằm ở 3.000 ký tự mà ở chỗ
   mỗi tờ hướng dẫn là một section duy nhất với tới 50 chunk cùng một header. Tách tờ hướng dẫn theo
   heading markdown có sẵn (trung bình 16 heading mỗi tờ, tên chuẩn như "Thành phần", "Cách dùng -
   Liều dùng", "Chống chỉ định") sẽ đưa leaflet về cùng cấu trúc với Dược thư, mỗi section một
   intent. Sau đó có thể thử chunk 4.000 đến 6.000 ký tự bằng một ablation rẻ.
2. **Benchmark có rò rỉ gợi ý vào câu hỏi.** 1.514 câu mang hậu tố "(phần <nhãn>)", trong đó nhóm
   chunk_risk chèn cả câu đầu của chunk gold vào câu hỏi. Đây là lỗi phải sửa trước mọi run mới, và
   số retrieval của bài v1 trên các nhóm leaflet và chunk_risk đang được lợi từ nó.
3. **Nhiều nhãn nhóm không đúng với mô tả trong bài.** "patient_natural" là template trên tên sản
   phẩm, không phải câu hỏi bệnh nhân tự nhiên; "noisy" là 259/300 câu của nhóm khác bỏ dấu; độ khó
   gán theo loại mục chứ không theo câu, nên "hard" có Hit@10 cao hơn "easy".
4. **Bộ golden e2e và corpus không có lỗi cấu trúc**: `e2e golden check` sạch, mọi gold section tồn
   tại, mọi nhãn chunk khớp chunker hiện tại, validation corpus không có lỗi. Golden kế thừa 50 câu
   có hậu tố "(phần ...)" từ benchmark.

## 2. Chunk và section

| Chỉ số | Giá trị |
| --- | --- |
| Section | 12.326, chunk 24.955 |
| Section chỉ một chunk | 9.597 (78 %) |
| Section bị tách | 2.729, trong đó leaflet 2.086 / 2.406, Dược thư 612 / 9.881, chương chung 31 / 39 |
| Section dài hơn 3.000 / 6.000 / 16.000 ký tự | 2.696 / 1.708 / 696 |
| Section dài nhất | bảng tra cứu biệt dược 823.165 ký tự, 278 chunk; các leaflet lớn 84.000 đến 124.000 ký tự, 32 đến 50 chunk |
| Ký tự mỗi chunk p10 / p50 / p90 / max | 156 / 1.994 / 2.964 / 3.000 |
| Chunk dưới 300 / dưới 100 ký tự | 4.765 / 1.430 |
| embedding_text, ký tự p50 / p90 / max | 2.141 / 3.133 / 3.598 |
| Token Qwen3-Embedding mỗi embedding_text p50 / p90 / p99 / max | 657 / 1.017 / 1.264 / 1.759 |
| Ký tự mỗi token (tiếng Việt, tokenizer Qwen3) p10 / p50 / p90 | 2,61 / 3,14 / 3,48 |
| Chunk vượt 2.048 token | 0 |

Nhận xét.

- Chunk hiện tại nằm gọn trong slot 2.048 token của llama.cpp trên Kaggle và còn cách xa giới hạn
  32k của Qwen3-Embedding và Qwen3-Reranker. Về mặt model, tăng lên 6.000 ký tự (khoảng 2.000 token)
  vẫn được nếu embedding chạy qua API, nhưng sẽ vượt slot 2.048 token của cấu hình Kaggle hiện tại.
- 78 % section đã là một chunk, nên tăng max_chars chỉ tác động lên leaflet và các bảng phụ lục. Với
  leaflet, vấn đề là cấu trúc: toàn bộ tờ là một section, chunk cắt theo ký tự nên chunk thứ hai trở
  đi mất heading ("### 2. Công dụng" chỉ còn trong text của chunk đầu), header context của mọi chunk
  đều là `<tên sản phẩm> > Thông tin chi tiết`.
- Leaflet có heading markdown chuẩn: 2.406 tờ, p50 16 heading, chỉ 1 tờ không có heading. Các heading
  phổ biến: thành phần 2.405, thông tin thêm 2.388, bảo quản 2.373, cách dùng - liều dùng 2.370,
  chống chỉ định 2.291, công dụng (chỉ định) 2.284, tác dụng phụ 2.253, hạn dùng 2.201, quá liều
  2.116, dược lý 2.045, nhà sản xuất 1.990, thận trọng 1.020, tương tác thuốc 991, thai kỳ 972.
- 1.430 chunk dưới 100 ký tự là mục Dược thư rất ngắn (ví dụ "Tên thương mại"); chúng đáng được gộp
  với mục kề hoặc giữ nguyên nhưng không nên tính là lỗi.
- Ngân sách bằng chứng của agent là 24.000 ký tự, tức 8 chunk 3.000 ký tự; chunk lớn hơn nghĩa là ít
  nguồn hơn trong một câu trả lời. Chi phí rerank tỷ lệ với độ dài cặp.

Khuyến nghị: (a) tách leaflet theo heading thành section con, header context thành
`<sản phẩm> > <heading>`; (b) giữ 3.000 ký tự làm mặc định; (c) chạy ablation kích thước chunk
2.000 / 3.000 / 4.500 / 6.000 trên benchmark đã sửa, embedding qua OpenRouter (25.000 chunk × 700 token
≈ 17 triệu token ≈ 0,35 USD mỗi cấu hình), rerank trên Kaggle hoặc DeepInfra; chọn theo nDCG@10 và
chi phí rerank. Việc này nhập vào pha retrieval của spec như thí nghiệm D7.

## 3. Benchmark retrieval 10.000 câu

### 3.1 Rò rỉ gợi ý vào câu hỏi

| Dạng rò rỉ | Số câu | Nhóm |
| --- | --- | --- |
| Hậu tố "(phần <nhãn>)" | 1.514 | leaflet 757, chunk_risk 673, formulary 84 |
| Có dấu ngoặc bất kỳ | 3.235 | brand_template 1.749, chunk_coverage 907, colloquial_alias 143, lexical 125, natural 96, paraphrase 95, clinical 50, template 32, noisy 24, confuser 14 |
| Câu chứa nguyên heading của section gold | 893 | formulary 663, multi_intent 166, noisy 48, chunk_risk 16 |
| Câu chứa nguyên tiêu đề tài liệu | 8.855 | formulary 4.843, leaflet 2.000, chunk_risk 963, multi_intent 500, noisy 475, patient_natural 74 |

Nguồn trong mã: `make_leaflet_row` và `make_colloquial_alias_row` nối `(phần {label})` với
`label = leaflet_label_for_category(chunk_body_text(chunk), category)`; `auto_query_for_chunk`
(nhóm chunk_coverage) nối `(phần {chunk_context_label(chunk)})`, và nhãn này là câu đầu của chunk,
ví dụ "(phần Rối loạn vận mạch: Tăng huyết áp)", "(phần Không có sự khác biệt có ý nghĩa giữa
etoricoxib và diclofena...)". Nhóm brand_lookup trong formulary cũng để đáp án trong ngoặc:
"ten biet duoc nay la hoat chat gi? (CARBOPLATIN - Tên thương mại)", "ABACAVIR là thuốc gì? (phần
Ziagen.)".

Hệ quả: Hit@k của leaflet (97,4 % Hit@3) và chunk_risk (87,3 %) được lợi từ text gold có sẵn trong
câu hỏi. Chứa tên thuốc trong câu là hợp lý với tra cứu thuốc, nhưng với leaflet "tên tài liệu" là
tiêu đề marketing của trang bán hàng ("Fordia 850 mg trị đái tháo đường type 2 kết hợp ăn kiêng và
thể thao (10 vỉ x 10 viên)"), không phải cách người dùng gọi thuốc.

Sửa: bỏ mọi hậu tố "(phần ...)" và đáp án trong ngoặc; với chunk_coverage, thay bằng câu hỏi theo
intent của heading chứa chunk (có được sau khi tách leaflet theo heading); với leaflet, dùng tên
sản phẩm chuẩn hóa (thương hiệu + hàm lượng + dạng) thay tiêu đề marketing, giữ tiêu đề đầy đủ ở
một tập con nhỏ có nhãn riêng.

### 3.2 Gold ở mức section quá rộng với leaflet

Với 1.921 câu leaflet có `retrieval_granularity = section`, 1.554 câu có section gold gồm nhiều
chunk (p50 của leaflet khoảng 5 chunk, tối đa 50). `is_hit` tính trúng khi chunk lấy được thuộc
section gold, nên câu hỏi về liều dùng được tính trúng nếu lấy được chunk thành phần của cùng sản
phẩm. Nhóm patient_natural (500 câu, 440 câu gold nhiều chunk) đạt Hit@3 100 % một phần vì vậy.
Chỉ 1.550 câu chunk_window và 269 câu chunk_exact đo đúng vị trí. Tách leaflet theo heading sửa
được gốc rễ: section gold trở thành đúng mục trả lời.

### 3.3 Nhãn nhóm và độ khó không đúng với mô tả trong bài

- `patient_natural`: sinh từ `PATIENT_QUERY_TEMPLATES` trên tên sản phẩm ("{product} có thành phần
  gì?"), trùng cách sinh với brand_template; bài v1 gọi là "naturally phrased patient questions".
  Đổi tên thành `leaflet_short_template` hoặc bỏ nhóm, và nếu muốn có câu hỏi bệnh nhân thật thì
  phải viết tay hoặc lấy từ người dùng.
- `noisy`: 259/300 câu là bản bỏ dấu của câu đã có ở nhóm khác. Đây là thiết kế chấp nhận được
  nhưng bài phải mô tả đúng là "biến thể bỏ dấu của câu hỏi hiện có", và nên bổ sung lỗi chính tả
  thật (gõ sai, viết tắt) thay vì chỉ bỏ dấu.
- `confuser`: 200 câu chỉ thêm cụm "Trong các thuốc cùng nhóm, ..." vào câu hỏi thường; không có
  thuốc gây nhiễu thật trong câu. Bài v1 mô tả là "look-alike drug names" là không đúng.
- `lexical`: câu hỏi là một câu nguyên văn trong section ("Khi tiêm adenosin, trước khi về hẳn
  nhịp xoang..."), đúng nghĩa known-item lexical; giữ nhưng mô tả đúng.
- Độ khó gán theo `SECTION_CATEGORY_RULES` cho loại mục, không theo câu; kết quả Hit@10 easy 98,6 %,
  hard 99,5 %, medium 97,3 %. Bỏ trường này khỏi bài hoặc định nghĩa lại theo quan sát (ví dụ theo
  Hit của BM25).
- Intent mất cân đối: general_info 2.792 câu, trong khi atc_lookup 2, table_lookup 21, guidance 33.
  Bài v1 nói "17 intents" nhưng ba intent gần như không có mẫu. Gộp general_info thành các intent
  cụ thể (quá liều, bảo quản, dược lý, thông tin chung) vì template của chúng đã tách sẵn.

### 3.4 Những thứ đúng

- 10.000 câu không trùng văn bản; mọi `expected_section_ids` tồn tại trong corpus; 9.400 nhãn
  `expected_chunk_id` khớp chunker hiện tại (nhãn một-based `chunk-001`).
- Nhãn relevance cho 1.126 câu formulary chấp nhận chunk leaflet cùng hoạt chất theo heading; luật
  trong `relevance_judgments.py` rõ ràng và có phiên bản.
- Multi-intent 500 câu ghép hai mục của cùng chuyên luận với template cố định; đúng với mô tả.

### 3.5 Trùng lặp sản phẩm

545 chunk text xuất hiện nguyên văn ở nhiều leaflet (cùng thuốc khác hàm lượng hoặc quy cách);
157 trong 3.900 câu họ leaflet có chunk gold trùng văn bản với một leaflet khác, nên ranking đúng
nội dung vẫn có thể bị chấm sai sản phẩm. 88 họ sản phẩm có từ 2 đến 4 biến thể (Coveram 4,
Jardiance Duo 3, Glucophage XR 3). Sửa bằng cách mở rộng `any_acceptable` cho các câu này hoặc
chấp nhận chunk trùng văn bản trong relevance judgments.

## 4. Bộ golden e2e

- `e2e golden check` sạch: 500 item, 420 answerable (70 × 6 nhóm), 50 multi-turn, 10 + 10 + 10.
- 50 item answerable kế thừa hậu tố "(phần ...)" (leaflet 24, chunk_risk 26) và 116 item có dấu
  ngoặc (phần lớn là quy cách đóng gói trong tiêu đề sản phẩm). Khi sửa benchmark, các item này phải
  viết lại và chạy lại; các run v1 giữ làm tham chiếu.
- Multi-turn 50 item đúng cấu trúc (3 lượt, lượt cuối chỉ thuốc bằng "thuốc này"), nhưng 48/50 là
  formulary và câu trả lời giả lập của lượt 2 do tác giả viết; lớp hội thoại 1.500 câu trong spec
  sẽ bổ sung các hiện tượng còn thiếu.
- Injection, out-of-scope, unanswerable chỉ 10 mỗi loại; spec đã nâng lên 50.

## 5. Việc đề xuất cho pha dữ liệu (trước pha 0 của spec)

1. Tách leaflet theo heading markdown thành section con, chuẩn hóa tên heading về bộ intent (bảng
   ánh xạ đã có trong `relevance_judgments.py`), header context `<sản phẩm> > <heading>`. Bump
   `CHUNKER_VERSION`, re-embed, release mới.
2. Sinh lại benchmark: bỏ mọi hậu tố và đáp án trong ngoặc; chunk_coverage hỏi theo intent của
   heading; leaflet dùng tên sản phẩm chuẩn hóa; đổi tên patient_natural; thêm lỗi chính tả thật cho
   noisy; confuser dùng tên thuốc gây nhiễu thật (cặp look-alike từ danh sách thuốc); bỏ hoặc định
   nghĩa lại độ khó; tách general_info; mở rộng any_acceptable cho sản phẩm trùng văn bản.
3. Chạy lại toàn bộ bảng retrieval trên benchmark mới (các run v1 vô hiệu vì gold đổi), kèm ablation
   kích thước chunk.
4. Viết lại 50 item golden có hậu tố, giữ các item khác; chạy lại A1 và A2 Qwen3.5-9B trên release
   mới làm mốc v2.
5. Ghi vào bài: mô tả đúng từng nhóm, và một đoạn "so với v1" giải thích vì sao số retrieval thay đổi.

## 6. Chunk v2 (2026-10-15)

Chunk là đơn vị đọc (spec §3.0c): `chunk_document` gộp các mục liền kề của một tài liệu tới
`TARGET_CHUNK_CHARS = 4200`; mục dài hơn `MAX_CHUNK_CHARS = 5600` được cắt riêng và các mảnh của nó
được gói lại tới `MAX_CHUNK_CHARS`. Đo bằng tokenizer Qwen3 (`qwen3-embedding-0.6b-q8_0.gguf`,
llama.cpp `server-b10920`, endpoint `/tokenize`) trên bundle `data/corpus/formulary` (3.120 tài
liệu, 34.552 mục).

| Đo | n | mean | p50 | p90 | p99 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| chunk_text | 13.412 | 1.001 | 1.054 | 1.599 | 2.224 | 3.098 |
| embedding_text | 13.412 | 1.072 | 1.133 | 1.687 | 2.264 | 3.214 |
| chunk_text, Dược thư | 3.095 | 1.086 | 1.159 | 1.760 | 2.263 | 2.466 |
| chunk_text, tờ hướng dẫn | 10.317 | 976 | 1.022 | 1.587 | 2.006 | 3.098 |

- 6.973 chunk (52 %) chứa từ hai mục trở lên; 93 chunk dưới 64 token (tài liệu chỉ có một mục ngắn).
- Không chunk nào vượt slot embed 4.096 token; chunk dài nhất là bảng tờ hướng dẫn, vì bảng tốn
  khoảng 1,8 ký tự mỗi token so với khoảng 3,2 của văn xuôi.
- Các mức target đã thử (ký tự, số chunk, mean token): 3.600 cho 14.649 chunk, khoảng 920 token;
  4.200 cho 13.412, 1.001 đo thật; 4.800 cho 12.443, khoảng 1.080; 5.400 cho 11.663, 1.152 đo thật.
  Mean thấp hơn target vì nhiều tài liệu ngắn hơn target, nên chunk cuối của tài liệu luôn non.
- Trước khi gói các mảnh của mục dài, mục dài bị cắt theo từng block: 386 chunk dưới 64 token, có
  chunk chỉ còn câu dẫn mà bảng nằm ở chunk khác.
- Benchmark dựng lại: 10.000 câu, nhóm formulary 5.000, leaflet 2.500, structured 1.000,
  leaflet_short 500, multi_intent 500, noisy 500; query_form `section_coverage` 1.000. Không câu nào có
  "(phần", không trùng text, không gold ngoài bundle; 564 mục gold dài hơn `MAX_CHUNK_CHARS` trải trên
  nhiều chunk, các mục còn lại nằm trong đúng một chunk. Relevance judgments: 1.140 dòng.
