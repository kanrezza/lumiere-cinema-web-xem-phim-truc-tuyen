# Quyền riêng tư và xử lý sự cố

## Yêu cầu của người dùng

Chạy migration và khai báo email liên hệ do đơn vị vận hành quản lý qua `PRIVACY_CONTACT_EMAIL`. Chính sách hiển thị ở [`/privacy/`](http://127.0.0.1:8000/privacy/) và được liên kết từ trang đăng ký và chân trang. Cập nhật nội dung và phiên bản trong mã khi thay đổi bên xử lý, mục đích hoặc thời hạn giữ dữ liệu. Kiểm tra lại dịch vụ đang dùng, nhất là email, VNPay, YouTube, STUN/TURN và phụ đề.

1. Trong **Tài khoản → Quyền riêng tư**, người dùng xác nhận bằng mật khẩu hiện tại, nhận mã yêu cầu và có thể hủy trước khi xử lý.
2. Trong **Studio → Quyền riêng tư** tại `/admin/privacy/`, superuser xem xét yêu cầu. Đối chiếu các giao dịch đang chờ, nghĩa vụ giữ dữ liệu, quyền VIP và kênh liên hệ với người gửi trước khi xác nhận. Chuyển trường hợp tài khoản quản trị hoặc tranh chấp đang xử lý sang người phụ trách.
3. Khi xác nhận, Lumière vô hiệu hóa tài khoản, thay thông tin nhận diện, dọn hoạt động gắn với tài khoản, bỏ liên kết người yêu cầu trong tác vụ phụ đề và vô hiệu hóa quyền trên phiên cũ. Hệ thống giữ đơn hàng, tham chiếu đối soát và bản ghi xử lý. Callback thanh toán đến muộn vẫn ghi nhận giao dịch và quyền truy cập của tài khoản đã ẩn danh vẫn bị vô hiệu hóa.
4. Trên bộ lọc **Đã xử lý hồ sơ**, kiểm tra tác vụ xóa ảnh đại diện. Nếu kho ảnh lỗi, nút **Thử xóa ảnh lại** chạy lại thao tác. Người vận hành xử lý yêu cầu tương ứng ở nơi lưu ảnh bên ngoài, hệ thống cũ, bản sao lưu và bên tích hợp theo phạm vi đang dùng.

Ghi thời gian, mã yêu cầu, quyết định và người xử lý. Áp dụng lịch lưu giữ đã thống nhất cho bản sao lưu, log, dữ liệu đối soát và bằng chứng xử lý. Nếu phục hồi bản sao cũ, giữ hệ thống cách ly, đối chiếu các yêu cầu đã hoàn thành sau ngày sao lưu và áp dụng lại chúng trước khi mở truy cập. [Hướng dẫn sao lưu và phục hồi](BACKUP_RESTORE.md)

## Khi phát hiện sự cố dữ liệu

1. **Ghi nhận.** Mở phiếu sự cố ở kênh nội bộ giới hạn quyền, ghi thời điểm phát hiện, người phụ trách, hệ thống liên quan và dấu hiệu đầu tiên. Giữ bằng chứng cần thiết ở kho riêng. Sử dụng mã hồ sơ thay cho thông tin nhận diện trong kênh trao đổi chung.
2. **Khoanh vùng.** Xác định tài khoản, tệp, dịch vụ tích hợp hoặc khóa liên quan. Tạm dừng luồng bị ảnh hưởng nếu cần. Thu hồi khóa đã lộ, vô hiệu hóa phiên liên quan và ghi các hành động đã làm. WAF và log máy chủ là các nguồn bằng chứng riêng.
3. **Đánh giá tác động.** Lập danh sách loại dữ liệu, số người có thể bị ảnh hưởng, khoảng thời gian, bên xử lý và khả năng truy cập tiếp diễn. Bàn giao người phụ trách quyền riêng tư xác định đối tượng, điều kiện và thời hạn thông báo theo văn bản áp dụng. [Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15](https://vanban.chinhphu.vn/?docid=214590&pageid=27160) · [Nghị định 356/2025/NĐ-CP](https://vanban.chinhphu.vn/?docid=216387&pageid=27160)
4. **Phục hồi.** Vá nguyên nhân, chạy kiểm thử có liên quan, xác minh quyền truy cập và khôi phục trên môi trường cách ly nếu cần. Chỉ mở lại dịch vụ sau khi người phụ trách xác nhận các ca kiểm tra đạt.
5. **Đóng sự cố.** Lưu diễn biến, quyết định thông báo, các bằng chứng cần giữ và công việc phòng tái diễn. Rà soát thời hạn lưu của bản sao phục vụ điều tra cùng người chịu trách nhiệm.

Trước khi nhận dữ liệu thật, phân công người trực, điền địa chỉ liên hệ vận hành, xác định bên xử lý thực tế và diễn tập một tình huống bằng dữ liệu mẫu.
