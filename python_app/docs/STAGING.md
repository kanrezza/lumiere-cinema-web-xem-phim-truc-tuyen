# Kiểm tra trước khi phát hành

GitHub Actions kiểm tra mỗi pull request và mỗi lần cập nhật nhánh `main`. Job **Build and test** cài thư viện từ các file khóa, kiểm tra kiểu và build Vue, kiểm tra migration Django, chạy test Django và Node. Job **HTTPS staging smoke** dựng một môi trường tạm riêng, kiểm thử qua TLS, diễn tập khôi phục trong workspace riêng rồi dọn các container và volume của runner. [Workflow CI](../../.github/workflows/ci.yml) · [Diễn tập khôi phục](BACKUP_RESTORE.md)

## Staging HTTPS trên máy

Yêu cầu Docker Engine hoặc Docker Desktop đang chạy, Docker Compose, Python 3 và FFmpeg để giải mã đoạn video trong smoke test. Từ thư mục gốc repo, chạy:

```sh
cd python_app/deploy/staging
python3 init_env.py
./manage.sh build
./manage.sh up -d --wait --wait-timeout 240
./manage.sh exec -T gateway cat /data/caddy/pki/authorities/local/root.crt > /tmp/lumiere-staging-root.crt
python3 smoke.py --ca /tmp/lumiere-staging-root.crt --decode
```

Gateway chỉ lắng nghe ở loopback. Mở [https://localhost:8443/](https://localhost:8443/) sau khi thêm chứng chỉ CA thử nghiệm vào hồ sơ trình duyệt dùng để kiểm thử. Smoke test đọc CA trực tiếp, xác minh chứng chỉ và hostname. Tài khoản `staging-host` và `staging-viewer` dùng mật khẩu ngẫu nhiên trong file `python_app/deploy/staging/.env` do máy tạo. File này cũng chứa khóa thử nghiệm và chỉ chủ file có quyền đọc/ghi.

Staging chạy Django với `DEBUG=0`, MySQL và Redis riêng, tự tạo hai tập phim gốc bằng FFmpeg và hai track phụ đề. Gateway phục vụ tài nguyên frontend và kho ảnh công khai. Kho video riêng chỉ có trong container ứng dụng. Staging không gửi email và không dùng tài khoản hay cơ sở dữ liệu đang hoạt động.

Smoke test xác thực các luồng sau:

- Phiên đăng nhập bảo mật và bundle frontend được tải qua HTTPS.
- Vé phát phim, playlist HLS, đoạn video được FFmpeg giải mã và track WebVTT được phục vụ qua endpoint có quyền.
- Chủ phòng tạo phòng, tài khoản thứ hai được duyệt và nhận trạng thái phát từ hai phiên HTTPS độc lập.
- Gửi lại cùng biểu mẫu VIP giữ nguyên mã đơn. Ứng dụng xác nhận callback có chữ ký bằng khóa fixture và xử lý callback lặp đúng một lần. Đích checkout dùng tên miền dành riêng `payments.example.invalid`.

Dừng môi trường bằng `./manage.sh down`. Volume được giữ để lần sau dùng lại dữ liệu fixture. Chỉ dùng `./manage.sh down -v` khi muốn xóa toàn bộ dữ liệu staging của project này.

## Staging công khai và VNPay Sandbox

Để kiểm tra trên hai mạng thật, triển khai trên máy chủ staging riêng với tên miền và chứng chỉ được trình duyệt tin cậy. Dùng database, Redis, kho video và secret dành riêng cho staging. Cấu hình reverse proxy như mẫu triển khai, đặt `DEBUG=0`, khai báo `PUBLIC_ORIGIN`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` theo tên miền và giữ cổng Gunicorn chỉ trong mạng riêng. Dùng video có quyền sử dụng. [Mẫu Nginx](../deploy/nginx.conf.example) · [Hướng dẫn triển khai](../README.md#triển-khai-thực-tế)

| Hạng mục | Cách xác nhận trên staging công khai |
| --- | --- |
| Phát phim | Đăng nhập trên desktop và điện thoại. Mở phim thử, phát qua ít nhất hai đoạn HLS, tua và bật phụ đề. Xác nhận nguồn vẫn phát khi chuyển tập và tiếp tục từ vị trí đã lưu. |
| Phòng xem | Chủ phòng dùng Wi-Fi, khách dùng dữ liệu di động hoặc mạng khác. Duyệt khách, cho hai thiết bị cùng phát, thử tua và chat. Bật mic cả hai phía, xác nhận nghe được qua hai mạng, khóa và mở mic khách. Cấu hình STUN/TURN riêng cho staging nếu cần. |
| VNPay Sandbox | Dùng thông tin merchant Sandbox thực do VNPay cấp. Khai báo `VNPAY_TMN_CODE`, `VNPAY_HASH_SECRET`, URL của Sandbox và địa chỉ nhận IPN `https://<tên-miền-staging>/payments/ipn/`. Thử một giao dịch thành công, một giao dịch bị hủy và một callback lặp theo môi trường Sandbox. Đối chiếu trạng thái từng đơn và hạn VIP trong Studio. |

Ghi kết quả theo commit, tên miền, trình duyệt và mạng sử dụng. Hai phiên trong smoke test kiểm tra phần điều phối của ứng dụng. Bài kiểm tra trên hai mạng thật còn bao gồm khả năng kết nối WebRTC qua NAT. Giao dịch qua Sandbox cần xác nhận từ VNPay trên URL staging công khai.
