# Lumière · Nền tảng xem phim trực tuyến

Lumière là ứng dụng Python/Django để khám phá phim, xem trực tuyến và tổ chức phòng xem chung. Ứng dụng nằm trong thư mục [`python_app/`](python_app/). Giao diện sử dụng Django Templates, HTML, CSS và JavaScript.

- **Khám phá phim:** Tìm kiếm tiếng Việt không dấu, lọc theo thể loại, quốc gia, năm và tình trạng có bản xem. Có trang diễn viên, trailer, điểm IMDb và đánh giá của người xem.
- **Xem phim:** Phát video HLS, chọn phụ đề SRT/WebVTT, lưu phim vào tủ phim và xem tiếp từ vị trí đã lưu. Có giao diện sáng và tối.
- **VIP và xem chung:** Có gói VIP tháng/năm và tích hợp VNPay. Chủ phòng có thể đồng bộ phát phim, đặt mật khẩu, duyệt khách và quản lý quyền bật mic. Thành viên có thể chat hoặc tham gia thoại.
- **Quản trị:** Lumière Studio theo dõi hoạt động và báo lỗi. Django Admin quản lý phim, tập, phụ đề, tài khoản và giao dịch. Bình luận bị gắn cờ được đưa vào hàng chờ để quản trị viên duyệt.

## Chạy trên máy

Cần **Python 3.12 trở lên**. Các lệnh dưới đây dùng Bash trên macOS, Linux hoặc WSL. Cài thêm **FFmpeg** có bộ mã hóa `libx264` và **ffprobe** trong `PATH` để tạo video demo hoặc xử lý video tải lên.

```bash
git clone https://github.com/kanrezza/lumiere-cinema-web-xem-phim-truc-tuyen.git
cd lumiere-cinema-web-xem-phim-truc-tuyen/python_app

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

test -f .env || cp .env.example .env
set -a
source .env
set +a

python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
./run-local.sh
```

Nếu đã có bản sao dự án, bắt đầu từ bước vào `python_app/` và giữ file `.env` hiện có. Để trống `DB_NAME` để dùng SQLite tại `python_app/db.sqlite3`. Script `run-local.sh` tự nạp `.env` khi khởi động web. Khi mở terminal khác để chạy lệnh `manage.py`, kích hoạt `.venv` và nạp lại `.env` như trên.

| Trang | Địa chỉ |
| --- | --- |
| Trang chào | [127.0.0.1:8000](http://127.0.0.1:8000/) |
| Khám phá phim | [/browse/](http://127.0.0.1:8000/browse/) |
| Lumière Studio | [/studio/](http://127.0.0.1:8000/studio/) |
| Django Admin | [/admin/](http://127.0.0.1:8000/admin/) |

Dùng tài khoản vừa tạo bằng `createsuperuser` để vào Studio và Admin. Đăng ký tài khoản thường trên trang web để thử luồng người xem.

## Thử phát và tải phim lên

`seed_demo` tạo danh mục phim và gói VIP minh họa. Để có video phát thử, mở terminal thứ hai, vào `python_app/`, kích hoạt `.venv` và nạp `.env`, rồi chạy một trong hai lệnh sau với `DEBUG=1`:

```bash
python manage.py make_demo_video   # Clip 20 giây cho Sau hoàng hôn
python manage.py make_demo_series  # Hai tập demo 30 giây, có phụ đề Việt và Anh
```

Đăng nhập rồi mở phim demo trong **Khám phá phim**. Với phim của bạn, vào **Admin → Phim** để tạo và công khai thông tin phim, rồi vào **Tập phim** để tải file MP4, MKV, MOV hoặc WebM lên. Chạy `python manage.py process_videos` sau khi tải lên để chuyển mã. Tập có thể phát khi chuyển sang trạng thái sẵn sàng (`ready`).

Video gốc và HLS được lưu riêng. Quyền phát được kiểm tra trên máy chủ và liên kết phát có thời hạn. Cơ chế này không thay thế DRM.

## Cấu hình thêm

- **MySQL và triển khai:** Đặt các biến `DB_*` để dùng MySQL. Môi trường `DEBUG=0` cần Redis. Có cấu hình mẫu cho Nginx, Gunicorn và worker trong [`python_app/deploy/`](python_app/deploy/).
- **VNPay:** Điền thông tin merchant Sandbox và cấu hình địa chỉ HTTPS nhận IPN để thử thanh toán. Thông tin merchant và khóa bí mật được giữ trong môi trường riêng.
- **Phụ đề tự động và thoại:** Nhận dạng lời thoại và dịch phụ đề dùng hai dịch vụ local tùy chọn. Thoại qua WebRTC có thể cấu hình máy chủ STUN/TURN khi thành viên kết nối từ các mạng khác nhau.

Xem [hướng dẫn kỹ thuật](python_app/README.md) để thiết lập các tích hợp trên, nhập dữ liệu cũ hoặc triển khai.

## Kiểm thử

Chạy trong `python_app/` với môi trường Python đã kích hoạt và `.env` đã được nạp:

```bash
python manage.py check
python manage.py test cinema cinema.audit_experience_cases
```

Nếu đã cài Node.js, chạy thêm `node --test tests/*.test.cjs` để kiểm tra trình phát và các tương tác JavaScript.

## Cấu trúc dự án

- [`python_app/cinema/`](python_app/cinema/) — Mô hình dữ liệu, nghiệp vụ, quản trị, migrations, lệnh xử lý video và kiểm thử Django.
- [`python_app/config/`](python_app/config/) — Cấu hình Django và định tuyến.
- [`python_app/templates/`](python_app/templates/) và [`python_app/static/`](python_app/static/) — Giao diện và tài nguyên trình duyệt.
- [`python_app/services/`](python_app/services/) — Dịch vụ nhận dạng và dịch phụ đề tùy chọn.

Phát triển bởi **Trần Đình Danh** · Phenikaa University.
