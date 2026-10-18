# Soạn bộ golden E2E

Hướng dẫn này là quy trình soạn `data/evaluation/e2e/golden_e2e.jsonl` (schema `e2e-golden-v2`).

## Quy trình

```bash
uv run pharma-lab e2e golden sample              # ghi authoring/*.todo.jsonl (270 answerable, 50 multi-turn)
uv run pharma-lab e2e golden hard-candidates --run hybrid-qwen4b-v2-p50-k20-rrf2   # ứng viên multi-hop từ benchmark
uv run pharma-lab e2e golden generate            # ứng viên hai thuốc và biệt dược sang hoạt chất, sinh từ corpus
uv run pharma-lab e2e golden draft               # nháp các câu multi-hop còn thiếu quota bằng LLM, ghi multi-hop-NN.draft.jsonl để duyệt
uv run pharma-lab e2e golden answerable-candidates   # câu answerable theo nhóm (natural.todo.jsonl) và theo lát cắt (slice.todo.jsonl)
uv run pharma-lab e2e golden multi-turn-candidates   # câu multi-turn lấy từ nhóm conversational của benchmark
uv run pharma-lab e2e golden draft --family multi-turn  # nháp câu multi-turn còn thiếu quota, ghi multi-turn-NN.draft.jsonl
uv run pharma-lab e2e golden draft --family natural  # nháp câu answerable còn thiếu quota mỗi nhóm, ghi natural-NN.draft.jsonl
uv run pharma-lab e2e golden draft --family slice    # nháp câu lát cắt còn thiếu quota, ghi slice-NN.draft.jsonl
uv run pharma-lab evaluation assemble           # benchmark đúng 10.000 câu: nhóm sinh bằng luật cắt cho vừa, cộng colloquial, glossary, conversational, multi_hop, safety; mọi câu golden là một dòng của nó
# soạn mỗi lô X.todo.jsonl thành X.authored.jsonl, cộng thêm multi-hop-NN và special.authored.jsonl
uv run pharma-lab e2e golden check data/evaluation/e2e/authoring/X.authored.jsonl
uv run pharma-lab e2e golden build               # kiểm đủ số lượng, ghi golden_e2e.jsonl và manifest
uv run pharma-lab data push --kaggle-account acc1 --message "Add the E2E golden set"
```

Mỗi dòng của `*.todo.jsonl` là một slot:

- `slot_id`: `item_id` của câu sẽ soạn.
- `category`: nhóm của câu.
- `source_rows`: các dòng lấy từ bộ gold.
- `sections`: text đầy đủ của các section gold.
- `focus_chunks`: text của chunk mong đợi, tức phần của section mà câu hỏi nói tới.

Mỗi dòng của `*.authored.jsonl` là một `GoldenItem` JSON do tác giả soạn cùng dược sĩ.

## Quy tắc chung

- **Key fact** là một ý nguyên tử (liều, chỉ định, chống chỉ định, cách dùng...) mà câu trả lời đúng phải nêu. Mỗi câu có 1–5 key fact và chỉ gồm những ý trả lời đúng điều được hỏi.
- **`evidence_quote`** chép nguyên văn một đoạn ngắn (khoảng 5–30 từ) trong text section.
  - Chỉ khoảng trắng được chuẩn hóa. Dấu markdown (`**`, `|`, `-`) phải giữ đúng như trong section, nên hãy chọn đoạn văn thường, tránh ranh giới ô bảng.
  - `section_id` phải thuộc `gold_section_ids`.
- **`reference.answer`** là câu trả lời mẫu tiếng Việt, 1–4 câu, trả lời thẳng.
  - Không có câu miễn trừ kiểu "hỏi ý kiến bác sĩ".
  - Chỉ dùng thông tin có trong section.
- **Các trường lấy từ dòng nguồn:**
  - `source_query_id` = `query_id`;
  - `eval_group` giữ nguyên;
  - `tags` = `eval_tags`;
  - `gold_section_ids` = `expected_section_ids`.

## Theo nhóm

- **`answerable`**
  - `turns` là đúng một lượt `user` với nguyên văn `query`.
  - `expected_behavior` là `grounded`.
  - `answer_mode = any_acceptable`: key fact lấy từ section trả lời trực tiếp nhất.
  - `answer_mode = multi_required`: key fact phải phủ mọi ý được hỏi, lấy từ các section tương ứng.
- **`multi_hop`** (150 câu, `grounded`, id `e2e-mhop-`): câu mà một lượt tìm kiếm (hybrid + rerank, top 5) thiếu một phần section gold, nên phải có vòng judge-refine mới đủ bằng chứng. Mỗi loại nhắm vào một phần của harness và được báo riêng.
  - `tags` có đúng một loại, quota cố định trong `MULTI_HOP_QUOTAS`: `retrieval_miss` 25 (câu sạch một mục mà vòng đầu trượt), `noisy_retry` 25 (câu nhiễu hoặc gõ sai mà vòng đầu trượt; hai loại này gồm mọi câu trượt mà người duyệt giữ, vì một vòng hybrid và rerank ít khi trượt), `three_intent` 16 (đa intent, các mục gold rơi vào hai chunk), `two_drug` 48 (mục tương tác của chuyên luận A nêu tên thuốc B, hỏi dùng chung và một ý về B), `brand_to_ingredient` 36 (tờ hướng dẫn của biệt dược thiếu mục được hỏi, Dược thư của hoạt chất có).
  - Ba loại đầu lấy từ `authoring/multi-hop.todo.jsonl` do `golden hard-candidates` ghi: mỗi dòng có câu benchmark, loại và các section gold mà vòng đầu bỏ sót (`missing`). `retrieval_miss` chỉ nhận câu có dấu hỏi và mọi section gold đủ thông tin (không phải tên thương mại, thông tin quy chế, tương kỵ, nội dung hay thông tin thêm; ít nhất 30 từ), vì phần lớn câu trượt của benchmark rơi vào các mục đó và không trả lời được từ chúng. Hai loại sau, và phần `three_intent` còn thiếu, lấy từ `authoring/multi-hop.generated.jsonl` do `golden generate` sinh từ corpus (mặc định gấp đôi quota để bù câu bị loại khi duyệt): câu hỏi ghép theo mẫu, kèm `subjects` là tên thuốc mà câu viết lại phải giữ. Câu `three_intent` sinh theo luật hỏi ba mục của một chuyên luận nằm ở ít nhất hai chunk, mỗi thuốc một câu và bỏ qua thuốc mà các câu `three_intent` đã soạn dùng.
  - `golden draft` đếm số câu đã soạn mỗi loại trong `multi-hop-NN.authored.jsonl`, nháp phần còn thiếu quota, bỏ ứng viên mà batch `*.authored.jsonl` hoặc `*.draft.jsonl` đã dùng (câu bị loại không được nháp lại), thứ tự theo `--seed`, ghi thành batch mới đánh số tiếp theo. Mỗi câu một lời gọi `gemini-3.1-flash-lite` (`--model`) trên endpoint LLM của backend, soạn câu trả lời mẫu và key fact; với câu sinh theo luật, model viết lại câu hỏi cho tự nhiên. Bản nháp được kiểm bằng luật của `golden check` cộng điều kiện mọi section gold có ít nhất một key fact và câu viết lại còn nêu đủ tên thuốc; bản lỗi được gửi lại kèm danh sách lỗi một lần, vẫn lỗi thì lấy ứng viên kế tiếp cùng loại và ghi vào `multi-hop.failed.jsonl`. Duyệt xong các batch nháp rồi mới chạy `draft` lần nữa.
  - Bản nháp chưa phải bản soạn: người duyệt (Claude Fable 5.1 trong vai dược sĩ, theo rubric) duyệt từng câu trong `multi-hop-NN.draft.jsonl` (câu hỏi có cần đủ mọi section không, key fact có đúng và đủ không), sửa rồi lưu thành `multi-hop-NN.authored.jsonl`. `golden build` chỉ đọc file `*.authored.jsonl` và kiểm số câu mỗi loại đúng quota.
  - `turns` là đúng một lượt `user`; key fact phải có quote từ mọi section gold, kể cả section vòng đầu bỏ sót.
  - `eval_group` để trống.
- **Nhóm answerable theo benchmark.** Mỗi câu answerable có `eval_group` là một nhóm của benchmark retrieval: 30 câu cho mỗi nhóm trong sáu nhóm sinh bằng luật, `colloquial` 20 (gọi sản phẩm chỉ bằng alias dân dã vắng trong tờ hướng dẫn) và `glossary` 10 (cụm lời thường cho thuật ngữ mà mục chỉ ghi viết tắt), mỗi câu là một dòng của benchmark qua `source_query_id`, giữ nguyên câu hỏi. Câu thiếu quota được bốc ngẫu nhiên trong nhóm từ `authoring/natural.todo.jsonl` (`golden answerable-candidates`), nháp bằng `golden draft --family natural` (id `e2e-ans-n`) và duyệt như multi-hop; quota đếm theo `eval_group` của mọi câu answerable ngoài lát cắt, ở bất kỳ batch nào. Nhờ vậy bảng e2e theo nhóm khớp bảng retrieval theo nhóm.
- **Lát cắt answerable** (60 câu, id `e2e-ans-s`, `tags` có đúng một lát, giữ `eval_group` của dòng nguồn, chỉ lấy từ sáu nhóm sinh bằng luật): `header_dependent` 20 (mục gold không nêu tên thuốc, chỉ header của chunk mang tên), `low_overlap` 20 (câu hỏi ít trùng từ với mục gold), `sibling_products` 20 (cùng thương hiệu và hoạt chất, khác hàm lượng hoặc dạng, có cùng mục). Lát cắt định nghĩa từ câu hỏi và corpus (trường `slices` của benchmark), không từ kết quả của hệ thống nào, nên câu được bốc ngẫu nhiên trong lát từ `authoring/slice.todo.jsonl`, nháp bằng `golden draft --family slice` và duyệt như multi-hop.
- **Multi-turn** (50 câu, id `e2e-mt-`, `eval_group = conversational`, `tags` có đúng một hiện tượng): lấy từ nhóm `conversational` của benchmark qua `golden multi-turn-candidates`, quota theo hiện tượng (pronoun 7, ellipsis 7, sáu hiện tượng còn lại 6). Lịch sử hội thoại giữ nguyên từ benchmark, người duyệt chỉ sửa đáp án và key fact.
- **`unanswerable`** (10 câu, `abstain`)
  - Hỏi về thuốc hoặc hoạt chất có thật nhưng không có trong corpus.
  - `absent_terms` ghi tên thuốc và hoạt chất; `golden check` xác nhận chúng không xuất hiện trong bất kỳ section hay tiêu đề nào.
- **`out_of_scope`** (10 câu, `redirect`): câu hỏi rõ ràng không liên quan đến thuốc, như nấu ăn, thời tiết, lập trình, thể thao, du lịch.
- **`injection`** (10 câu, `blocked`)
  - Câu hỏi có dáng hỏi thuốc nhưng chèn lệnh tấn công, ví dụ:
    - bỏ qua mọi hướng dẫn trước;
    - in system prompt;
    - đóng vai một trợ lý không giới hạn;
    - xuất khóa API;
    - trả lời bằng nội dung độc hại.
  - Các câu phải đa dạng về kỹ thuật.
