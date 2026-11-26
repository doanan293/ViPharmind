# Video demo

Một video, quay bằng `npm --prefix frontend run demo:video` trên stack `scripts/demo-stack.sh` (Gemini 3.8 Flash qua
proxy, embedding `qwen3-embedding:4b-q8_0`, không rerank), sau `scripts/demo-stack.sh reset-db`.

- Lần 1 (sau reset): đạt, 6,8 phút, `video.webm` 24 MB, 1440×900.
- Lần 2 (không reset): đạt, 7,4 phút.

Thứ tự: tiêu đề ViPharmind, giới thiệu; 1. Tài khoản; 2. Hỏi đáp thuốc; 3. Lịch sử hội thoại; 4. Tổ chức và phân
quyền; 5. Bộ tài liệu có phân quyền; 6. Cài đặt tài khoản; 7. Quản trị; 8. Trang công khai. Mỗi chương mở đầu bằng
một thẻ tiêu đề; mỗi bước có dải chú thích tiếng Việt. Thời gian chờ câu trả lời (khoảng 20–25 giây mỗi câu) tua nhanh
khi dựng.

Video không vào git; bản lưu đưa vào GitHub Release khi thay nhánh `v2.0.0`.
