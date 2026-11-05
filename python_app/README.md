# Lumière Python

Bản rebuild Django của hệ thống phim online. Nằm riêng trong `python_app/`; ứng dụng Laravel và database cũ chưa bị thay thế. Python xử lý backend; giao diện vẫn dùng HTML, CSS, JavaScript.

## Đã có trong bản này

- Giao diện sáng/tối responsive, khám phá/tìm kiếm/lọc phim, chi tiết phim, tủ phim và lịch sử xem.
- Trailer công khai bằng MP4 hoặc YouTube; phân biệt phim chiếu rạp, bản phim sẵn sàng và video giới thiệu.
- Đăng ký, đăng nhập, đăng xuất bằng POST, đổi/quên mật khẩu, hồ sơ và kiểm soát quyền quản trị.
- Đánh giá 1–5, bình luận, báo lỗi video và quản trị Django cho phim/tập phim/người dùng/gói/giao dịch; bảng thống kê tại `/studio/` dành cho staff.
- Upload MP4/MKV/MOV/WebM vào kho riêng; worker FFmpeg kiểm tra nội dung và chuyển thành HLS H.264/AAC tối đa 720p.
- Nguồn phát yêu cầu đăng nhập, quyền phim/VIP và token gắn với phiên có thời hạn 10 phút. Bộ phát làm mới nguồn sau 8 phút.
- VIP tháng/năm, VNPay 2.1.0, đơn hàng lưu snapshot giá/thời hạn, IPN có xác minh HMAC-SHA512, số tiền và merchant; xử lý lặp không cấp VIP thêm.
- Xem chung: tài khoản đăng nhập, VIP tạo tối đa 3 phòng hoạt động, tối đa 10 thành viên hoạt động/phòng, timeout hiện diện 30 giây, có nút rời phòng, phòng tồn tại 6 giờ, chủ phòng điều khiển phim, chat, loại thành viên, kết thúc phòng. Đồng bộ bằng polling 2 giây.
- Lệnh nhập Laravel chỉ đọc source, mặc định dry-run, giữ mapping để chạy lại không nhân bản dữ liệu.

Đây là nền tảng chạy được để tiếp tục phát triển. Chưa có DRM thương mại, chuyển mã nhiều chất lượng, phụ đề, thông báo tập mới, CDN/object storage, hoàn tiền tự động hoặc đăng ký VIP tự gia hạn. Các phim, artwork và giá gói tạo bởi `seed_demo` là minh họa; không đi kèm video thương mại.

## Chạy trên máy

Yêu cầu Python 3.12 trở lên, FFmpeg/ffprobe có trong `PATH`. Bộ dependencies khóa trong `requirements.txt`; môi trường hiện tại đã dùng Python 3.14. Không cần PHP, Composer hoặc Node cho bản Python.

```bash
cd python_app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Mở `.env` và sửa cấu hình. Ứng dụng đọc biến môi trường, **không tự tải `.env`**. Với file `.env` của chính bạn, có thể export trước mỗi lần chạy:

```bash
set -a
source .env
set +a
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

Có thể chạy `python manage.py make_demo_video` để tạo clip kiểm tra 20 giây cho phim minh họa **Sau hoàng hôn** (chỉ hoạt động với `DEBUG=1`). Sau khi thiết lập, `./run-local.sh` nạp `.env` và mở server local.

Mở `http://127.0.0.1:8000/`; admin tại `/admin/`. Không tạo tài khoản admin/mật khẩu mặc định. `DB_NAME` trống dùng SQLite riêng trong `python_app/db.sqlite3`. `seed_demo` chỉ thêm dữ liệu mẫu, không xóa dữ liệu đang có. Email quên mật khẩu khi `DEBUG=1` hiện trong terminal; triển khai thật cần SMTP.

## Upload và phát phim

1. Đăng nhập `/admin/`, tạo Movie, chọn thể loại, poster và quyền VIP; bật `published` khi muốn công khai thông tin.
2. Thêm Episode, chọn Movie, số tập, tên tập và file video. Dung lượng mặc định tối đa 4 GiB, cấu hình bằng `MAX_VIDEO_BYTES`.
3. Chạy worker trong terminal khác, cùng môi trường và database:

   ```bash
   python manage.py process_videos
   ```

4. Khi trạng thái chuyển thành `ready`, đăng nhập tài khoản có quyền để phát từ trang chi tiết phim. Nếu lỗi, kiểm tra định dạng rồi chạy `python manage.py process_videos --episode ID --retry-failed`.

Worker kết thúc khi xử lý xong các mục đang chờ; local chạy lại sau mỗi đợt upload. Production dùng service/timer mẫu trong `deploy/`. Chạy FFmpeg dưới tài khoản riêng, giới hạn CPU/RAM/dung lượng và chặn Internet ra ngoài, chỉ mở kết nối database cần thiết. Không chạy worker bằng root. Không bật thư mục `private_media` làm static/media trên web server; cả file gốc lẫn HLS đều riêng tư. Xóa metadata phim/tập không đồng nghĩa dọn toàn bộ file; cần chính sách kiểm kê/dọn file có kiểm soát trước khi dùng lâu dài.

## Trailer và phim chiếu rạp

Sau khi chạy `migrate` (bao gồm `0006_movie_trailers_and_cinema` và `0007_movie_trailer_credit`), mở Movie trong `/admin/`:

1. Đánh dấu **Phim chiếu rạp** nếu phù hợp. Đây là phân loại do quản trị chọn, không có nghĩa phim hiện còn chiếu ngoài rạp.
2. Chọn **một** nguồn: liên kết YouTube HTTPS hoặc file MP4. Xóa nguồn cũ trước khi đổi loại; không dán HTML iframe.
3. Điền **Nguồn/ghi công trailer** khi cần. Chỉ sử dụng nội dung có quyền phát hành; trường ghi công hỗ trợ văn bản và liên kết được escape.

MP4 tối đa 50 MiB, thời lượng trên 0 đến 5 phút, một luồng H.264, tối đa một luồng âm thanh AAC và kích thước tối đa 4096×2160. Server kiểm tra nội dung bằng `ffprobe`; đổi đuôi file không đủ. Trailer không đi qua worker chuyển mã, vì vậy cần chuẩn bị file tương thích trước khi upload. Chỉ nhân viên có quyền thêm/sửa Movie mới upload trailer qua admin. File dùng tên UUID trong kho **public** `MEDIA_ROOT/trailers`, tách khỏi Episode và kho phim riêng tư. Thay/xóa metadata không tự dọn mọi file trailer cũ; áp dụng chính sách dọn file có kiểm kê như kho video.

Trang `/movies/<slug>/trailer/` mở cho khách khi phim đã công khai và có nguồn hợp lệ. YouTube chỉ tải iframe sau khi bấm Phát trailer, dùng `youtube-nocookie.com`; CSP chỉ cho phép nguồn iframe này. Nhà cung cấp có thể giới hạn nhúng/xóa video, khi đó người xem có liên kết mở YouTube. Phát được một video bên ngoài vẫn cần kiểm tra thực tế.

Trailer không cấp quyền xem phim, VIP, ticket HLS hoặc tiến độ bản đầy đủ. Phim chưa có tập `ready` vẫn ghi **Đang chuẩn bị/Chưa có bản xem**, dù có trailer. **Phim chiếu rạp** và **Có trailer** là hai nhãn độc lập với trạng thái này; chưa có dữ liệu lịch phát hành để tự gọi là “Sắp chiếu”.

Các bộ lọc có thể kết hợp với tìm kiếm, thể loại, quốc gia, năm và phân trang:

- `/browse/?availability=ready`: đã có bản phim sẵn sàng.
- `/browse/?availability=upcoming`: chưa có bản xem trong thư viện.
- `/browse/?release=cinema`: phim được quản trị phân loại chiếu rạp.
- `/browse/?trailer=1`: phim có nguồn trailer.

Thêm đoạn giới thiệu mẫu có sẵn, không tải nguồn ngoài:

```bash
python manage.py seed_trailer_demo
```

Lệnh thêm đoạn trích **16 giây** từ Big Buck Bunny, ghi công Blender Foundation và CC BY 3.0; đây là clip demo, không phải trailer chính thức. Chạy lại giữ nguyên trailer đã có; không tạo tập phim, cấp quyền hoặc tự gắn nhãn chiếu rạp. Bản phim đầy đủ vẫn cần upload/xử lý riêng. Nguồn tài sản tại [static/imagery/SOURCES.md](static/imagery/SOURCES.md).

Bản khảo sát giao diện Chợ Phim, phạm vi kiểm chứng và thứ tự cải thiện nằm tại [docs/CHOPHIM_REVIEW.md](docs/CHOPHIM_REVIEW.md).

## VNPay

Ứng dụng chưa có merchant credentials; không tạo đơn hàng hay thu tiền khi thiếu cấu hình. Không có endpoint “thanh toán thành công giả” để tự cấp VIP.

1. Đăng ký thông tin merchant/Sandbox với VNPay, điền `VNPAY_TMN_CODE` và `VNPAY_HASH_SECRET` trong môi trường riêng.
2. Dùng `VNPAY_URL=https://sandbox.vnpayment.vn/paymentv2/vpcpay.html` trong giai đoạn kiểm thử.
3. Đặt `PUBLIC_ORIGIN` bằng HTTPS domain có thể truy cập từ VNPay; localhost không nhận được IPN từ bên ngoài.
4. Đăng ký IPN `https://<domain>/payments/ipn/` với VNPay. Return URL tự tạo là `https://<domain>/payments/return/`.
5. Kiểm tra thanh toán thành công/thất bại/hủy, callback lặp, sai chữ ký, sai số tiền và gia hạn. Trình duyệt quay về return URL **không** cấp VIP; chỉ IPN hợp lệ mới thay đổi quyền.
6. Chỉ đổi sang endpoint production và merchant production sau khi VNPay xác nhận tích hợp và các bài thử thực tế đã đạt.

Theo [tài liệu thanh toán VNPay 2.1.0](https://sandbox.vnpayment.vn/apis/docs/thanh-toan-pay/pay.html), tích hợp sử dụng số tiền VND nhân 100 và ký tập tham số đã sắp xếp bằng HMAC-SHA512. Các test trong repository kiểm tra logic với dữ liệu ký tổng hợp; chưa thay thế thử giao dịch Sandbox thật. Giá 59.000đ/30 ngày và 599.000đ/365 ngày chỉ là mẫu, sửa trong admin trước khi bán.

## MySQL và chuyển dữ liệu Laravel

Tạo **database đích mới** (ví dụ `lumiere_python`) bằng `utf8mb4`, đặt `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, rồi chạy `migrate`. Không chạy Django migrations lên database Laravel đang dùng. Sao lưu source và destination trước khi nhập. File `database/sql/lumiere.sql` trong checkout hiện trống nên không thể khôi phục dữ liệu từ file đó.

Lệnh nhập kết nối trực tiếp database Laravel, chỉ đọc các bảng trong danh sách cố định và mở transaction READ ONLY. Tạo MySQL user chỉ có quyền `SELECT` cho source; điền các biến `LEGACY_DB_*` trong `.env`. `LEGACY_SOURCE_ID` phải giữ nguyên qua các lần nhập cùng nguồn. Lệnh không đọc `.env` của Laravel và không thực thi SQL dump.

```bash
# Mặc định kiểm tra toàn bộ dữ liệu và rollback destination.
python manage.py import_laravel
# Xem báo cáo trước, sau đó mới ghi destination.
python manage.py import_laravel --apply
```

Quy tắc chuyển:

- Giữ người dùng/email, trạng thái hoạt động/khóa, tên/hồ sơ; tên đăng nhập được cấp theo dạng `legacy_<mã-nguồn>_<id>`. Có thể đăng nhập bằng email cũ hoặc tên đăng nhập mới. Email trùng với tài khoản đích chưa có mapping làm lệnh dừng; không tự gộp tài khoản.
- Bcrypt Laravel `$2y$`, `$2b$`, `$2a$` được xác thực bằng hasher tương thích, sau lần đăng nhập đúng chuyển thành hash Django mới. Hash không hỗ trợ được đặt không dùng được; quản trị viên cần trợ giúp đặt mật khẩu. Session/token cũ không chuyển.
- Quyền admin cũ **không tự cấp lại**. Sau khi xác minh danh tính, cấp `is_staff` và quyền thích hợp trong Django admin; chỉ cấp superuser cho người thực sự cần.
- Giữ thể loại, diễn viên, phim/tập phim, quan hệ thể loại, bình luận, đánh giá, yêu thích và lịch sử. Đánh giá Laravel thang 10 được đổi sang thang 5 bằng `ceil(score/2)`; trường `rating` tổng hợp cũ không nhập vì tính từ đánh giá mới.
- Lịch sử cũ chỉ biết phim đã xem: gắn với tập đầu, vị trí 0 giây, giữ thời điểm cũ. Không có dữ liệu tiến độ để phục hồi.
- URL video cũ không nhập/lấy về. Tập được tạo với trạng thái cần upload; admin upload file rồi chạy worker. Phim chưa có tập được tạo tập “Phim đầy đủ”.
- Poster/avatar cũ, số điện thoại và các trường sở thích dạng text/JSON chưa có mapping trong mô hình mới; tải lại poster thủ công. Bio cắt tối đa 500 ký tự, bình luận 1.000 ký tự, tên phim 200 ký tự theo giới hạn bản mới.
- Mapping `LegacyRecord` giữ nguồn/bảng/ID cũ → ID mới, giúp chạy lại không nhân bản và không ghi đè nội dung đã sửa. Dữ liệu source thay đổi sau lần nhập đầu không được đồng bộ tự động; đây là lệnh chuyển một lần, không phải replication.

Kiểm thử importer dùng snapshot giả lập, chưa chạy với MySQL thật của bạn. Hãy thử trên bản sao database trước khi chuyển chính thức.

## Giới hạn bảo vệ video

HLS là định dạng phát phân đoạn, **không phải DRM và không ngăn tuyệt đối người có quyền xem lưu lại nội dung**. Token/phiên/kiểm tra VIP giúp chặn truy cập trái phép, link hết hạn và chia sẻ link không kèm phiên; người dùng đã được cấp quyền vẫn có thể trích xuất dữ liệu trong lúc xem hoặc quay màn hình. Watermark HTML và `controlslist=nodownload` là răn đe/giao diện, không phải biện pháp chống sao chép mạnh.

Mỗi tài khoản chỉ có một browser session được cấp ticket hiện hành; nhiều tab dùng cùng session vẫn có thể hoạt động. Phòng xem chung yêu cầu mỗi người có quyền với phim đó. Muốn bảo vệ nội dung thương mại mạnh hơn cần DRM (Widevine/FairPlay/PlayReady), dịch vụ cấp license và quy trình xử lý nội dung phù hợp — chưa nằm trong bản này.

## Triển khai thực tế

- Dùng HTTPS, `DEBUG=0`, secret ngẫu nhiên tối thiểu 50 ký tự, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `PUBLIC_ORIGIN` đúng domain, MySQL và Redis riêng tư. Production bắt buộc có `REDIS_URL` để rate limit/phiên phát dùng chung giữa workers.
- Giữ Gunicorn chỉ lắng nghe loopback/private network. `TRUST_PROXY=1` và `TRUSTED_PROXY_IPS` chỉ khi reverse proxy tin cậy ghi đè `X-Forwarded-Proto`/`X-Real-IP`; chặn mọi truy cập trực tiếp tới Gunicorn.
- Cấu hình SMTP, backup MySQL và kho file, giám sát dung lượng/log worker. Không log query string của `/stream/` vì chứa ticket, không log secret/VNPay hash secret.
- `deploy/` có mẫu Nginx, systemd web service, video service và timer. Thay domain, TLS certificates, đường dẫn, UID/GID theo máy thật; không chạy nguyên mẫu mà chưa kiểm tra. Reverse proxy giới hạn request/upload trước Django; upload vẫn cần quota ổ đĩa.
- File `/etc/lumiere/env` chỉ cho service user đọc; secret không đặt trong Git. Kho private và kho public là hai thư mục khác nhau; quyền filesystem phải phù hợp với service và Nginx.
- Chạy `python manage.py collectstatic --noinput`, `python manage.py check --deploy`, kiểm thử với `DEBUG=0`, rồi mới khởi động services. Check deployment cần môi trường production hợp lệ.
- Chưa có kiểm toán bảo mật độc lập, đánh giá tải, DRM hay bài thử thanh toán thật. Cần kiểm tra thực tế MySQL, Redis, Nginx, storage/worker và VNPay trước khi mở cho người dùng.

Các tùy chọn bảo mật dựa trên [deployment checklist của Django](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/); luôn cập nhật bản vá dependencies và FFmpeg.

## Tìm kiếm và trạng thái nội dung

Tìm phim và diễn viên hỗ trợ chữ hoa tiếng Việt, không dấu và Unicode dạng tách dấu. Tìm phim bao gồm tên, mô tả và tên diễn viên được gắn với phim công khai. Dữ liệu chuẩn hóa được lưu trong database, tự cập nhật qua `save()`; migration `0004_normalized_search_fields` tạo dữ liệu cho các bản ghi cũ. Chạy `python manage.py migrate` trước khi khởi động phiên bản này.

`QuerySet.update()`, `bulk_create()`, `bulk_update()` và SQL trực tiếp không gọi `save()`. Nếu import/sửa tên hoặc mô tả bằng các cách đó, cập nhật cả trường tìm kiếm hoặc chạy lại khi không có thao tác chỉnh sửa nội dung đồng thời:

```bash
python manage.py reindex_search
```

Lệnh chạy theo batch, hỗ trợ `--database` và `--batch-size`. Truy vấn chuỗi con hiện vẫn quét dữ liệu ở database; các trường chuẩn hóa chưa thay thế full-text search cho thư viện lớn.

Danh mục có bộ lọc năm, kết hợp với các bộ lọc khác và giữ năm khi phân trang/đổi thể loại/quốc gia. Phim chưa có tập `ready` hiển thị “Đang chuẩn bị”; xem nhanh không tạo liên kết phát cho phim đó. Hero trang khám phá chỉ chọn phim có tập sẵn sàng. Quyền VIP/đăng nhập tiếp tục được kiểm tra tại server.

## Giao diện và thành viên VIP

Nút mặt trời/mặt trăng trên header chuyển giữa giao diện sáng và tối. Lựa chọn được lưu trong localStorage của trình duyệt (`lumiere-theme`), áp dụng trước khi tải stylesheet và giữ khi đổi trang/tải lại. Mặc định giữ giao diện tối; nếu trình duyệt chặn lưu trữ, nút vẫn đổi giao diện cho trang hiện tại. Hero/ảnh phim và trình phát giữ bảng màu tối để bảo đảm tương phản; không dùng bộ lọc đảo màu lên nội dung phim.

Thành viên còn hạn VIP mở `/vip/` sẽ thấy quyền lợi/hạn dùng và các lối vào phim VIP, xem chung, tủ phim. Bảng giá chỉ xuất hiện khi chủ động mở liên kết Gia hạn (`/vip/?renew=1`). Khách, tài khoản thường và gói hết hạn vẫn có luồng mua. Tham số `renew` không cấp VIP; quyền vẫn chỉ được thay đổi bởi xác nhận thanh toán hợp lệ hoặc quản trị.

## Ảnh đại diện

Trong Hồ sơ → Ảnh đại diện, chọn JPG/PNG/WebP tối đa 5 MB rồi bấm Lưu ảnh. Ảnh đã lưu dùng chung cho menu tài khoản và avatar bên trái hồ sơ. Có xem trước/hủy lựa chọn; thay đổi ảnh tách khỏi form họ tên/giới thiệu. Đánh dấu xóa và Lưu ảnh để dùng lại chữ cái mặc định.

Endpoint POST `/profile/avatar/` chỉ cập nhật tài khoản đang đăng nhập, có CSRF. Ảnh được kiểm tra nội dung/kích thước, áp dụng hướng EXIF, cắt giữa thành 512×512 WebP và bỏ metadata; ảnh động không được chấp nhận. File lưu tại `MEDIA_ROOT/avatars` với tên UUID. Chỉ dọn ảnh do chức năng này tạo và không còn được tham chiếu, sau commit. Quyền upload video vẫn dành cho nhân viên có quyền phù hợp; quyền upload avatar chỉ áp dụng cho endpoint này.

Chạy `python manage.py migrate` để áp dụng `0005_user_avatar` khi triển khai. Storage/publicmedia cần được phục vụ như các ảnh poster hiện có. Kiểm thử avatar sử dụng MEDIA_ROOT tạm, không thay ảnh thật của người dùng.

## Kiểm thử

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test cinema
# Chạy thêm bộ ca chấp nhận từ đợt audit.
python manage.py test cinema cinema.audit_experience_cases
```

Bộ test kiểm tra quyền video, chữ ký/phiên/hạn token, VIP hết hạn, CSRF, XSS escaping, quyền điều khiển phòng, giới hạn phòng, callback VNPay, dữ liệu nhập, trailer/upload/URL và bộ lọc nội dung. Local UI/video cần thêm kiểm tra trình duyệt với file thật; test tổng hợp không chứng minh chống tải tuyệt đối.
