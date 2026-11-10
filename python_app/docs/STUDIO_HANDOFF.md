# Lumière Studio — trạng thái bàn giao

Dashboard tại `/studio/` và `/admin/` dùng chung giao diện quản trị. Menu, danh sách, form và trang đăng nhập có cùng màu sắc, kiểu chữ và lựa chọn sáng/tối với website (`lumiere-theme`). Không cần migration mới cho đợt thay đổi này.

## Đã có

- Dashboard lấy số liệu thật, doanh thu chỉ tính đơn đã thanh toán; menu và dữ liệu được giới hạn theo quyền từng model.
- Form phim/tập phim chia nhóm tiếng Việt; tìm thể loại, diễn viên và phim bằng autocomplete. Form sửa tập phim giữ bảo vệ file gốc.
- Các danh sách có cột dễ đọc, tìm kiếm, bộ lọc, trạng thái trống và phân trang. Giao dịch vẫn chỉ đọc; việc cấp quyền giữ theo cơ chế Django hiện có.
- Kiểm tra trình duyệt: dashboard sáng/tối, tìm phim, xóa tìm kiếm, chọn thể loại, tạo slug, lỗi trường bắt buộc, bố cục 320 px và menu đóng bằng Escape. Không tạo nội dung thử trong database đang dùng.
- Toàn bộ 288 test Django đã đạt; 25 test quản trị được chạy lại sau các chỉnh sửa cuối và đều đạt. Các bài thêm/sửa dữ liệu chạy trên database kiểm thử.

## Tiếp tục tinh chỉnh

- Hoàn thiện bố cục form phim hai cột trên màn hình lớn. Các nhóm đã có class `studio-basic`, `studio-artwork`, `studio-relations`, `studio-trailer`, `studio-imdb`, `studio-publishing`; hiện vẫn xếp theo từng phần dọc.
- Rà soát thêm tablet, lịch chọn ngày, popup thêm đối tượng liên quan và các form ít dùng như nhóm quyền.
- Kiểm tra upload file thật qua giao diện mới trước khi triển khai; kiểm thử tự động hiện vẫn bảo vệ giới hạn upload và quyền truy cập.

Chạy lại kiểm thử từ thư mục `python_app`:

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py test cinema.test_admin_metadata cinema.test_studio_design
.venv/bin/python manage.py test cinema cinema.audit_experience_cases
```

Đăng nhập bằng tài khoản có `is_staff` và quyền phù hợp. Tài khoản VIP không có quyền quản trị. Mật khẩu, database, model nhận dạng và file phim không được lưu trong Git.
