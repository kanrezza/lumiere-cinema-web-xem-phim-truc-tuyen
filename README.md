# Lumière

**Nền tảng xem phim trực tuyến và tổ chức phòng xem chung.** Lumière cung cấp thư viện phim, trình phát có phụ đề và trải nghiệm xem cùng bạn bè. Lumière Studio là không gian quản trị danh mục, thành viên và hoạt động cộng đồng.

[Cài đặt trên máy](#cài-đặt-trên-máy) · [Thử phát phim](#thử-phát-phim) · [Kiểm thử](#kiểm-thử) · [Tài liệu kỹ thuật](python_app/README.md)

## Tính năng

| Khu vực | Chức năng |
| --- | --- |
| **Khám phá phim** | Tìm theo tên phim hoặc diễn viên, hỗ trợ tiếng Việt không dấu. Kết hợp bộ lọc thể loại, quốc gia, năm, phim chiếu rạp và tình trạng có bản xem. Trang chi tiết hiển thị trailer, điểm IMDb khi có dữ liệu và đánh giá cộng đồng. |
| **Trình phát** | Phát HLS, tua ±10 giây, chọn phụ đề SRT/WebVTT, tiếp tục từ vị trí đã lưu và chuyển tập. Có thể bật dịch vụ nhận dạng lời thoại và dịch phụ đề Việt – Anh. |
| **Tài khoản** | Lưu phim vào tủ phim, quản lý lịch sử xem, đổi ảnh đại diện và chọn giao diện sáng hoặc tối. |
| **Phòng xem chung** | Đồng bộ phát, tạm dừng và tua theo chủ phòng. Phòng có chat, thoại WebRTC, tùy chọn mật khẩu và duyệt thành viên. Chủ phòng có thể khóa mic của từng thành viên. |
| **Thành viên VIP** | Gói tháng và năm, quyền xem phim VIP và tạo phòng xem chung. Thanh toán tích hợp VNPay. |
| **Lumière Studio** | Theo dõi thư viện, người dùng, giao dịch và báo lỗi. Xem bình luận và đánh giá theo từng phim. Lọc bình luận theo lý do gắn cờ và duyệt trước khi hiển thị. |

## Kiến trúc

- **Python và Django** xử lý xác thực, phân quyền và dữ liệu. Django Templates dựng HTML ban đầu.
- **Vue 3, TypeScript và CSS** xây dựng giao diện người xem và Studio. Vite đóng gói mã theo nhóm trang để Django nạp qua manifest. Khi chạy local, chỉ cần khởi động Django sau khi build frontend.
- **SQLite** là cơ sở dữ liệu mặc định khi chạy local. Có thể cấu hình **MySQL** và dùng **Redis** cho giới hạn tần suất dùng chung khi triển khai.
- **FFmpeg** chuyển mã video sang HLS. **HLS.js** hỗ trợ phát trên trình duyệt và **WebRTC** truyền thoại trong phòng xem. Máy chủ kiểm tra quyền trước khi cấp liên kết phát có thời hạn.

## Cài đặt trên máy

Dùng **Python 3.12+**, **Node.js 22.12+** (kèm npm) và Git. Để tạo video mẫu hoặc xử lý tệp tải lên, cần thêm **FFmpeg** có bộ mã hóa `libx264` và **ffprobe** trong `PATH`. Các lệnh dưới đây dùng được trong Bash hoặc Zsh trên macOS, Linux và WSL.

### 1. Cài thư viện và build frontend

```bash
git clone https://github.com/kanrezza/lumiere-cinema-web-xem-phim-truc-tuyen.git
cd lumiere-cinema-web-xem-phim-truc-tuyen/python_app

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

test -f .env || cp .env.example .env
npm --prefix frontend ci
npm --prefix frontend run build
```

Nếu đã clone dự án, bắt đầu từ thư mục `python_app/`. File môi trường mẫu bật `DEBUG=1` và để trống `DB_NAME` để dùng SQLite.

### 2. Khởi tạo dữ liệu và chạy web

```bash
set -a
source .env
set +a

python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
./run-local.sh
```

`seed_demo` thêm danh mục phim và gói VIP mẫu. `createsuperuser` yêu cầu bạn tự đặt thông tin đăng nhập cho tài khoản quản trị.

| Trang | Địa chỉ |
| --- | --- |
| Trang chào | [127.0.0.1:8000](http://127.0.0.1:8000/) |
| Khám phá | [/browse/](http://127.0.0.1:8000/browse/) |
| Đăng ký tài khoản người xem | [/accounts/register/](http://127.0.0.1:8000/accounts/register/) |
| Lumière Studio | [/studio/](http://127.0.0.1:8000/studio/) |
| Django Admin | [/admin/](http://127.0.0.1:8000/admin/) |

`run-local.sh` tự nạp `.env`. Khi mở terminal khác để chạy lệnh `manage.py`, vào `python_app/`, kích hoạt `.venv` và nạp lại `.env` theo bước 2. Sau khi sửa mã trong `frontend/src/`, chạy lại `npm --prefix frontend run build`.

## Thử phát phim

Chạy các lệnh sau trong `python_app/` với `DEBUG=1`. Mỗi lệnh có thể chạy riêng.

```bash
python manage.py make_demo_video   # Sau hoàng hôn · video mẫu 20 giây
python manage.py make_demo_series  # Trạm ánh sáng (Demo) · hai tập có phụ đề Việt/Anh
```

Đăng nhập bằng tài khoản vừa tạo, mở **Khám phá** và chọn phim mẫu. Với bộ phim hai tập, bạn có thể thử đổi phụ đề, tua, chuyển tập và kiểm tra tiến độ bằng cách rời trang rồi mở lại.

Để phát phim của bạn, vào **Admin → Phim** để tạo và công khai thông tin phim, sau đó tải tệp MP4, MKV, MOV hoặc WebM lên trong **Tập phim**. Chạy `python manage.py process_videos` để chuyển mã. Tập sẽ phát được khi có trạng thái **Sẵn sàng** và tài khoản có quyền xem.

## Cấu hình và vận hành

| Nhu cầu | Thiết lập |
| --- | --- |
| **Cơ sở dữ liệu** | Để trống `DB_NAME` cho SQLite, hoặc điền nhóm `DB_*` cho MySQL. |
| **Triển khai** | Dùng khóa Django riêng, cấu hình tên miền HTTPS và `REDIS_URL` khi chạy với `DEBUG=0`. Build frontend trước `collectstatic`. Các cấu hình mẫu Nginx, Gunicorn và worker nằm trong [deploy/](python_app/deploy/). |
| **Thanh toán thử** | Cấu hình merchant VNPay Sandbox và endpoint HTTPS nhận IPN. |
| **Phụ đề tự động** | Cấu hình và chạy các dịch vụ nhận dạng lời thoại, dịch phụ đề local để bật hai chức năng trong trình phát. |
| **Thoại qua mạng** | Triển khai HTTPS và dùng `ROOM_VOICE_ICE_SERVERS` để khai báo STUN/TURN khi mạng của người dùng cần. |

Xem [mẫu cấu hình](python_app/.env.example) và [tài liệu kỹ thuật](python_app/README.md) để thiết lập từng tích hợp. Giữ khóa bí mật, thông tin merchant và tệp `.env` bên ngoài Git.

## Kiểm thử

Chạy từ `python_app/` sau khi cài môi trường Python, nạp `.env` và cài các gói npm.

```bash
npm --prefix frontend run build
node --test tests/*.test.cjs
python manage.py check
python manage.py test cinema cinema.audit_experience_cases
```

Lệnh build kiểm tra kiểu TypeScript trước khi đóng gói. Bộ kiểm thử Django gồm các luồng danh mục, tài khoản, quyền phát phim, phụ đề, thanh toán, kiểm duyệt và phòng xem chung.

## Cấu trúc mã nguồn

| Thư mục | Vai trò |
| --- | --- |
| [`python_app/cinema/`](python_app/cinema/) | Mô hình dữ liệu, nghiệp vụ, Django Admin, migrations và kiểm thử Django. |
| [`python_app/config/`](python_app/config/) | Cấu hình dự án và định tuyến. |
| [`python_app/frontend/`](python_app/frontend/) | Mã Vue, TypeScript và cấu hình Vite. |
| [`python_app/templates/`](python_app/templates/) và [`python_app/static/`](python_app/static/) | HTML do Django dựng, CSS và tài nguyên trình duyệt. |
| [`python_app/services/`](python_app/services/) | Dịch vụ nhận dạng và dịch phụ đề tùy chọn. |

**Trần Đình Danh** · Phenikaa University


