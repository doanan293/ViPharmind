# Thiết kế dữ liệu eval v3: benchmark 10.000 câu và golden 500 câu

Ngày 2026-10-18. Thay §3.0b, §3.1 và phần dữ liệu của §4 trong
`2026-10-14-paper-v2-design.md` khi được duyệt. Mọi số trong tài liệu này đo trên các run `-v2-` đã
xong (benchmark 10.000 câu sinh bằng luật, hybrid Qwen3-Emb-4B + BM25 RRF k=2, top 5) và trên hai
báo cáo review độc lập ở `pharma-lab/data/work/golden-review/review-{ablations,data-quality}.md`.

## 1. Chẩn đoán

### 1.1 Câu sai từ luật sinh (không phải câu khó)

| Lỗi | Số câu | Nguồn |
| --- | --- | --- |
| Câu "dán nguyên đoạn văn" có gold lệch mục (chunk → section map sai) | 81 | `lexical` formulary, `section_coverage` structured |
| Câu chung chung ("X là thuốc gì", "Tìm thông tin về X", "X có tác dụng phụ gì") gắn vào mục quy chế, tương kỵ hoặc hướng dẫn xử trí ADR | 479 | formulary, structured, noisy |
| Hỏi "có thai hoặc cho con bú" nhưng gold chỉ một mục | 222 | formulary, conversational |
| Tên sản phẩm bị cắt giữa chừng ("Agirenyl 5000IU phòng và có…") | 168 | leaflet, leaflet_short |
| colloquial: một alias trỏ nhiều sản phẩm; biến thể alias lặp; gold một dòng; câu trùng khác gold | 165 / 392 / 93 / 78 | luật colloquial |
| glossary: 68% là một thuật ngữ (TKTW); 8% mục đã viết đủ cụm lời thường | 150 / 18 | luật glossary |
| conversational: lịch sử là đoạn văn dán, câu trả lời cố định lấy sai mục; câu kiểu tiêu đề mục; trùng | 103 / 44 / 35 / 71 | kế thừa lỗi câu cha |
| multi_hop: "Tôi đang dùng" với thuốc tiêm, gây mê | ~30 | luật two_drug |

Những câu này không làm benchmark khó hơn, chỉ làm nhiễu: chúng hạ số của mọi cấu hình như nhau và
che chênh lệch giữa các tầng.

### 1.2 Hiệu ứng trần

Mỗi ablation chỉ đổi kết quả một lượt (gold trong top 5) ở một phần nhỏ số câu:

| Ablation | Tỉ lệ câu tầng đầy đủ thắng (toàn 10k) | Nhóm thắng nhiều nhất |
| --- | --- | --- |
| hybrid so với BM25 | 13,0% | noisy 33,2%, multi_intent 20,2%, structured 18,3% |
| enrichment so với không | 9,3% (không rerank); colloquial 28,9%, glossary 14,6% | leaflet 15,0%, structured 12,8%, noisy 12,2% |
| hybrid so với dense | 3,9% | leaflet_short 3,8% |
| rerank 4B so với không | 3,6% | noisy 10,2%, leaflet 5,4% |
| rerank 4B so với 0.6B / 8B | 1,0% / 0,7% (và thua 1,7% / 1,0%) | không nhóm nào |

Hệ quả cho bài: con số tổng trên benchmark sẽ nhỏ với mọi tầng trừ hybrid và enrichment. Đó là sự
thật của corpus này (retrieval đã gần trần), khớp với câu chuyện của bài, nhưng mỗi tầng cần một
**lát cắt mục tiêu** nơi hiệu quả của nó lộ rõ.

### 1.3 Lát cắt theo cách dựng câu tách được tầng

Đo trên 10k, lát cắt định nghĩa từ câu và corpus, không từ kết quả hệ thống:

| Lát cắt (định nghĩa) | Tầng | Tầng thắng trong lát | Ngoài lát |
| --- | --- | --- | --- |
| Mục gold không chứa tên thuốc/sản phẩm (chỉ header mang tên) | enrichment | 14,3% | 6,1% |
| Trùng từ câu hỏi và mục gold thấp (< 35%) | dense trong hybrid | 7,3% | 2,8% |
| Trùng từ thấp | hybrid so với BM25 | 15,6% | 11,2% |
| Biệt dược thuộc họ ≥ 3 sản phẩm cùng tên đầu | rerank | 4,1% | 3,5% |

Lát header và trùng từ tách tốt; lát "họ sản phẩm" chưa tách được rerank, cần định nghĩa sắc hơn
(cùng hoạt chất và cùng mục, khác hàm lượng hoặc dạng bào chế).

### 1.4 Probe chọn theo kết quả hệ thống là luẩn quẩn

`rerank_probe`, `lexical_probe`, `semantic_probe` được chọn ở chỗ tầng đó thắng, nên trên golden
chúng thắng theo định nghĩa (21/22 câu thắng ròng của rerank là probe; trên câu tự nhiên chênh gần
0). `retrieval_miss` và `noisy_retry` chọn ở chỗ hệ đầy đủ trượt, nên ở đó ablation lại thắng. Reviewer
sẽ bác cả hai.

## 2. Nguyên tắc

1. **Đúng trước, khó sau.** Mỗi câu phải: là câu người dùng thật có thể hỏi; hiểu được (kể cả qua
   lịch sử); mục gold trả lời đủ và chỉ những gì được hỏi. Đóng băng chỉ khi audit lấy mẫu mỗi nhóm
   (25 câu, người duyệt Fable) có tỉ lệ lỗi dưới 5%.
2. **Độ khó định nghĩa từ cách dựng câu, không từ kết quả hệ thống.** Mỗi tầng có một lát cắt mục
   tiêu định nghĩa bằng thuộc tính của câu và corpus; bài báo cáo số tổng và số trong lát.
3. **Một benchmark xuyên suốt.** Đúng 10.000 câu, golden 500 câu là các dòng của nó; mọi bảng
   retrieval và e2e theo cùng nhóm và cùng lát.
4. **Ngân sách.** Benchmark chỉ chấm bằng retrieval; mọi lời gọi LLM chỉ trên golden. Ngoại lệ ghi
   rõ: decision model Jev trên bộ hiệu chỉnh 300 + 100 câu (khoảng 0,2 USD, không sinh văn bản).
5. **Tách bộ hiệu chỉnh khỏi golden.** Bộ hiệu chỉnh ngưỡng không chứa câu nguồn của golden hay câu
   cha của câu multi-turn golden.

## 3. Benchmark 10.000 câu

### 3.1 Sửa luật sinh câu (thượng nguồn, `evaluation build`)

- Bỏ dạng câu "dán đoạn văn" (`lexical` dạng trích nguyên văn, `section_coverage` fill): không phải
  câu người dùng hỏi; thay bằng câu template cùng mục.
- Câu chung chung chỉ gắn vào `thong-tin-chung` hoặc `chi-dinh` (câu "là thuốc gì"),
  `tac-dung-khong-mong-muon-adr` (câu tác dụng phụ); không bao giờ vào `thong-tin-qui-che`,
  `tuong-ky`, `huong-dan-cach-xu-tri-adr`.
- Câu hỏi gộp thai kỳ và cho con bú: gold gồm cả `thoi-ky-mang-thai` và `thoi-ky-cho-con-bu`,
  `answer_mode = multi_required`; hoặc tách thành hai câu.
- Tên sản phẩm: dùng `brand_name` (cắt dạng bào chế và công dụng đúng ranh giới), không cắt giữa từ.

### 3.2 Nhóm và cỡ

| Nhóm | Cỡ | Tầng chứng minh | Ghi chú |
| --- | --- | --- | --- |
| formulary | ~3.100 | nền, hybrid, enrichment header | lấy mẫu theo intent và lát trùng từ |
| leaflet | ~1.550 | enrichment header, rerank (họ sản phẩm) | lấy mẫu theo lát header và họ sản phẩm |
| structured | 1.000 | chunk gộp, hybrid | sau khi bỏ câu dán đoạn |
| leaflet_short | 500 | nền | sau khi sửa tên cắt |
| noisy | 500 | hybrid (BM25 yếu), rerank, rephrase | |
| multi_intent | 500 | chunk gộp, judge đếm intent | |
| colloquial | ~400 | enrichment colloquial | sửa luật, mục 3.3 |
| glossary | ~300 | enrichment glossary | sửa luật, mục 3.3 |
| conversational | 1.500 | rephrase, D5 | sửa luật, mục 3.3 |
| multi_hop | 300 | judge + refine, graph so với ReAct | sửa luật, mục 3.3 |
| safety | 30 | guard | không có gold |

Cỡ formulary và leaflet là phần còn lại để tổng đúng 10.000.

### 3.3 Sửa các nhóm sinh thêm

- **colloquial**: một alias một sản phẩm (alias trỏ nhiều sản phẩm thì `any_acceptable` với gold là
  mục tương ứng của mọi sản phẩm); tối đa hai biến thể alias mỗi nhóm sản phẩm (ưu tiên alias ít trùng từ với tên); gold ít nhất 40 ký tự (bỏ câu rỗng kiểu "Không có."); bỏ alias
  là tên chính thức (tên tiếng Anh in trên hộp); trải trên mọi sản phẩm có alias.
- **glossary**: thêm thuật ngữ Dược thư viết tắt (ADR, HIV, AIDS, COX-2, ACE, PPI, SSRI, NSAID, MAO,
  TKTW, ECG, GFR, HBV, COPD, INR, QT, G6PD, LDL, HbA1c…) với cụm lời thường tự nhiên; mỗi thuật ngữ tối
  đa 25% nhóm; chỉ giữ mục chưa viết cụm lời thường.
- **conversational**: câu cha chỉ là câu dạng hỏi đã qua sửa 3.1; câu trả lời cố định lấy từ chính
  mục gold của câu lịch sử; thay câu kiểu tiêu đề ("còn thông tin chung thì sao") bằng câu tự nhiên;
  khử trùng (lượt cuối, gold); `topic_switch` ghi là đối chứng (lượt cuối là câu đầy đủ).
- **multi_hop**: bỏ vai "Tôi đang dùng" cho thuốc tiêm hoặc dùng trong bệnh viện, dùng câu hỏi trung
  tính; ghi `parallel` (two_drug) và `sequential` (brand_to_ingredient); `three_intent` đổi tên
  `multi_section`.

### 3.4 Thuộc tính lát cắt ghi trên từng dòng

Mỗi dòng có thêm trường `slices` tính khi assemble, không dùng kết quả hệ thống:

- `header_dependent`: mục gold không chứa từ đầu của tên thuốc/sản phẩm.
- `name_variant`: câu hỏi không viết nguyên văn chữ nào của tên thuốc/sản phẩm (gõ sai, không
  dấu, gọi cách khác). Thay `low_overlap`: độ trùng từ với mục gold không tách được lớp dense
  (mọi ngưỡng thử dưới 2 lần), tên thuốc thì tách được.
- `sibling_products`: sản phẩm có biến thể cùng hoạt chất và cùng mục, khác hàm lượng hoặc dạng
  (định nghĩa sắc hơn "họ sản phẩm"; cần kiểm lại tỉ lệ rerank thắng trước khi dùng).
- `multi_chunk`: các mục gold nằm ở từ hai chunk trở lên.

Báo cáo retrieval có bảng theo nhóm và bảng theo lát.

Kiểm trước trên run v2, 5.831 dòng không đổi, tỉ lệ dòng mà lớp thắng (top 5) trong và ngoài lát:

| Lát | Lớp (đủ so với bỏ) | Trong lát | Ngoài lát | Gấp |
| --- | --- | --- | --- | --- |
| header_dependent | hybrid so với plain | 14,0% | 5,6% | 2,5 |
| name_variant | dense so với BM25 | 46,2% | 14,1% | 3,3 |
| name_variant | hybrid so với BM25 | 41,0% | 12,9% | 3,2 |
| sibling_products | rerank 4B so với không rerank | 9,2% | 3,2% | 2,9 |
| multi_chunk | chunk gộp so với chunk theo mục | 34,4% | 10,1% | 3,4 |

Số chính thức đo lại trên run `-v3-` (Task 6).

## 4. Golden 500 câu

| Tầng golden | Cỡ | Cách chọn | Dùng cho |
| --- | --- | --- | --- |
| Tự nhiên | 30 × 6 nhóm luật + colloquial 20 + glossary 10 | ngẫu nhiên phân tầng trong nhóm | số không lệch, D6 |
| Lát cắt | 60 | theo thuộc tính `slices` (header_dependent 20, low_overlap 20, sibling_products 20), không theo kết quả hệ thống | hiệu quả tầng retrieval ở e2e |
| multi_hop sinh | 72 (sequential 42, parallel 30) | luật multi_hop đã sửa | graph so với ReAct, loop |
| multi_section | 16 | luật multi_section | judge đếm intent |
| trượt vòng 1 | 62 (retrieval_miss 32, noisy_retry 30) | hệ đầy đủ trượt vòng 1; chỉ báo chỉ số có điều kiện (tỉ lệ cứu) | loop |
| multi_turn | 50 | nhóm conversational, theo hiện tượng | rephrase |
| safety | 30 | như hiện nay | guard |

Thay đổi so với hiện tại: bỏ `rerank_probe`, `lexical_probe`, `semantic_probe` (chọn theo kết quả)
và thay bằng lát cắt theo thuộc tính; colloquial 20 và glossary 10 chọn lại sau khi sửa luật; multi_hop
chuyển sang sequential 42, parallel 30; thay câu golden có lỗi đã nêu (3 colloquial, 2 glossary, 3
multi_turn có lịch sử dán đoạn).

## 5. Quy tắc báo cáo (bài báo)

- Mọi khẳng định retrieval lấy từ benchmark 10k, có bảng theo nhóm và theo lát.
- Ablation trên golden báo theo tầng golden; D6 và các hàng retriever, reranker ở e2e chỉ trên tầng
  tự nhiên và multi_hop sinh; tầng trượt vòng 1 chỉ báo tỉ lệ cứu có điều kiện.
- Truthfulness báo cả số thô và số tái trọng số theo tỉ lệ nhóm benchmark.
- Khai báo trước các so sánh có kiểm định (loop: tất cả / multi_hop / cứu có điều kiện; τ: 0 so với τ*,
  τ* so với 1, Jev so với độ tin cậy nói ra) với Holm; Jev so với LLM judge là non-inferiority với biên
  3 điểm.
- D7 thêm so sánh cùng ngân sách token (mục ở k ≈ 15 so với chunk gộp k = 5).
- Reranker: chọn theo Hit@5 và Hit@1 trên 10k; 4B giữ vì Hit@1 cao hơn 0.6B 8 điểm và ngang 8B; nêu
  0.6B ngang ở Hit@5.

## 6. Kiểm chứng trước khi đóng băng

1. Audit lấy mẫu mỗi nhóm benchmark (25 câu, Fable): lỗi dưới 5%.
2. Bảng phân biệt: mỗi tầng có lát cắt mà tỉ lệ thắng trong lát ít nhất gấp đôi ngoài lát (đo trên
   run `-v3-`).
3. Golden: audit độc lập toàn bộ câu mới và mẫu 60 câu cũ.
4. `golden build` qua với kiểm tra mọi câu là dòng benchmark.

### 6.1 Sổ audit benchmark (Fable 5.1, rubric `data/work/benchmark-audit/audit-rubric.md`)

Mỗi vòng lấy mẫu mới 25 câu mỗi nhóm (275 câu), dựng lại benchmark sau mỗi lần sửa luật.

| Vòng | Lỗi | Tỉ lệ | Nhóm còn từ 5% | Luật sửa sau vòng |
| --- | --- | --- | --- | --- |
| 1 | 22/275 | 8,0% | colloquial 20%, noisy 16%, leaflet_short 12%, multi_hop 12% | gold rỗng, thai kỳ/cho con bú theo câu hỏi, tên cắt dở, alias phải có tên riêng, B là thuốc tương tác thật, lịch sử không trùng mục gold |
| 2 | 8/275 | 2,9% | structured 12%, leaflet 8%, leaflet_short 8% | tên cắt ở mọi vị trí, mục thay thế cùng thuốc, câu liều chỉ nhận mục liều, vắc xin không hỏi điều trị |
| 3 | 10/275 | 3,6% | formulary 12%, leaflet 8%, leaflet_short 8%, structured 8% | câu hỏi tên biệt dược giữ mục tên thương mại, mục thay thế trong cùng chuyên luận, bỏ tiêu đề dán, viết lại mẫu "người có thai hoặc có chống chỉ định" |
| 4 | 6/275 | 2,2% | leaflet 8% | câu "cần lưu ý gì" chỉ nhận mục thận trọng, sản phẩm dùng ngoài không ghép chuyên luận toàn thân |
| leaflet 5 | 3/50 | 6,0% | | "phòng," một từ vẫn là tên cắt, alias leaflet phải có tên riêng |
| leaflet 6 | 2/60 | 3,3% | | mục thay thế cùng thương hiệu, từ chỉ màu không là tên riêng |

Sau luật cuối, 110 câu leaflet đã audit ở hai vòng có chủ đích còn 1 lỗi (≈1%). Benchmark đóng băng
ngày 2026-10-18 bằng `evaluation assemble` (đúng 10.000 câu).

1. Sửa luật sinh câu benchmark gốc (3.1) và chạy lại `evaluation build`; giữ id câu cũ khi câu không
   đổi để cache dùng lại.
2. Sửa ba nhóm sinh thêm (3.3), thêm `slices` (3.4), assemble.
3. Audit benchmark (6.1); lặp tới khi đạt.
4. Golden: thay câu lỗi, chọn lại colloquial và glossary, tầng lát cắt, cân lại multi_hop; Fable duyệt;
   audit (6.3).
5. Chạy ma trận retrieval `-v3-`; kiểm bảng phân biệt (6.2).
6. Cập nhật spec, plan, Methods.
