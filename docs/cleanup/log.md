# Nhật ký làm sạch

Mỗi dòng: tính năng · triệu chứng · nguyên nhân · sửa · test.

## auth

- Trang đăng ký ghi "Tạo tài khoản bằng email hoặc Google" trong khi có thể có cả số điện thoại (local bật SMS) ·
  câu chữ cố định không theo các cách đăng nhập server bật · đổi thành "Tạo tài khoản để tra cứu thông tin thuốc."
  (vi, en), đúng ở mọi cấu hình · không cần test (chỉ đổi chữ).
- Nút và ô nhập cao 32 px, dưới 44 px trên màn cảm ứng (ảnh chụp 390×844) · cỡ mặc định của shadcn · xử lý chung ở
  bước thương hiệu và theme (Task 5) cho mọi trang, không sửa riêng từng form.
- Đăng ký email, sai mật khẩu, quên mật khẩu, đăng nhập bằng số điện thoại: chạy đúng trên stack demo (chương `auth`).
