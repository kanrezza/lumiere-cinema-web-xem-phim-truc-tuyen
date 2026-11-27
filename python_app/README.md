# Hướng dẫn kỹ thuật Lumière

Lumière dùng Python và Django cho máy chủ, Django Templates để dựng nội dung ban đầu và Vue 3 với TypeScript cho phần tương tác ở trang công khai, tài khoản, phòng xem và Studio. Tài liệu này trình bày các tính năng, tích hợp và cách vận hành ứng dụng. [Hướng dẫn cài đặt nhanh](../README.md)

[Cấu trúc code và quy tắc tái sử dụng](docs/ARCHITECTURE.md) mô tả các module backend theo nghiệp vụ, phần quản trị và luồng trạng thái/giao tiếp mạng của frontend.

## Đã có trong bản này

- Giao diện sáng/tối responsive, khám phá/tìm kiếm/lọc phim, chi tiết phim, tủ phim và lịch sử xem.
- Trailer công khai bằng MP4 hoặc YouTube; phân biệt phim chiếu rạp, bản phim sẵn sàng và video giới thiệu.
- Phụ đề SRT/WebVTT theo từng tập; CC luôn có lối vào, nhận dạng lời thoại và dịch Anh ↔ Việt bằng dịch vụ local tùy chọn; metadata IMDb có liên kết nguồn và ngày đối chiếu.
- Đăng ký, đăng nhập, đăng xuất bằng POST, đổi/quên mật khẩu, hồ sơ và kiểm soát quyền quản trị.
- Đánh giá 1–5, bình luận, báo lỗi video và quản trị Django cho phim/tập phim/người dùng/gói/giao dịch; bảng thống kê tại `/studio/` dành cho staff.
- Upload MP4/MKV/MOV/WebM vào kho riêng; worker FFmpeg kiểm tra nội dung và tạo HLS H.264/AAC nhiều mức chất lượng, tối đa 1440p theo nguồn gốc.
- Nguồn phát yêu cầu đăng nhập, quyền phim/VIP và token gắn với phiên có thời hạn 10 phút. Bộ phát làm mới nguồn sau 8 phút.
- VIP tháng/năm, VNPay 2.1.0, đơn hàng lưu snapshot giá/thời hạn, IPN có xác minh HMAC-SHA512, số tiền và merchant; xử lý lặp không cấp VIP thêm.
- Xem chung: tài khoản đăng nhập tạo tối đa 3 phòng hoạt động; chủ phòng miễn phí có tối đa 3 người/phòng, VIP/staff tối đa 10 người/phòng, tính cả chủ phòng; timeout hiện diện 30 giây, có nút rời phòng, phòng tồn tại 6 giờ, chủ phòng điều khiển phim, chat, loại thành viên, kết thúc phòng. Đồng bộ bằng polling 2 giây.
- Lệnh nhập Laravel chỉ đọc source, mặc định dry-run, giữ mapping để chạy lại không nhân bản dữ liệu.

Đây là nền tảng chạy được để tiếp tục phát triển. Chưa có DRM thương mại, chuyển mã nhiều chất lượng, thông báo tập mới, CDN/object storage, hoàn tiền tự động hoặc đăng ký VIP tự gia hạn. Các phim, artwork và giá gói tạo bởi `seed_demo` là minh họa; không đi kèm video thương mại.

## Chạy trên máy

Yêu cầu Python 3.12 trở lên và FFmpeg/ffprobe trong `PATH`. Các gói Python được khóa trong `requirements.txt`. Để build Vue, dùng Node.js 22.12 trở lên và chạy `npm --prefix frontend ci` rồi `npm --prefix frontend run build` từ `python_app/`.

Vite build các mục tải riêng cho điều hướng chung, Khám phá, trang tài khoản, trình phát/phòng xem và Studio. Django dùng manifest để nạp đúng tệp cho mỗi trang. HTML ban đầu giữ các liên kết, biểu mẫu, mã CSRF và thông báo kiểm tra dữ liệu từ máy chủ. TypeScript điều khiển cấp lại nguồn HLS, lưu tiến độ, tác vụ phụ đề, đồng bộ phòng và kết nối WebRTC. Thư viện HLS.js được nạp riêng trên trang phát.

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

Chạy `python manage.py make_demo_series` để tạo **Trạm ánh sáng (Demo)**, gồm hai clip màu 30 giây do FFmpeg tạo và phụ đề Việt/Anh để thử xem tiếp, đổi tập và ghi nhớ phụ đề. Lệnh yêu cầu `DEBUG=1`, xử lý clip qua worker HLS hiện có và công khai phim khi cả hai tập sẵn sàng. Chạy lại sẽ giữ file nguồn và phụ đề đã có.

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

## Gói thành viên, chất lượng video và công chiếu

| Quyền lợi | Thường | VIP |
| --- | --- | --- |
| Chất lượng tối đa | 720p | 1080p / 1440p khi nguồn hỗ trợ |
| Tạo phòng xem chung | 3 người gồm chủ phòng | 10 người gồm chủ phòng |
| Chat, mic, playlist, mật khẩu, duyệt khách | Có | Có |
| Phim VIP / suất công chiếu VIP | Không | Có |

Worker tạo HLS nhiều mức chất lượng thực, giữ đúng tỉ lệ và không nâng độ phân giải giả. Master playlist chỉ liệt kê các mức mà người xem được phép dùng; backend kiểm tra lại gói trên từng rendition và segment, kể cả khi VIP hết hạn giữa buổi xem. Nút **Cài đặt chất lượng và phụ đề** gom phụ đề/dịch và chất lượng vào một menu gọn. Menu có Tự động, các mức hiện có và ghi riêng chất lượng tối đa của phim với mức gói hỗ trợ. Trong phòng xem chung, chất lượng theo từng người, sức chứa theo chủ phòng. Video cũ chỉ có một rendition vẫn được kiểm tra độ phân giải thật; cần mã hóa lại để có thêm mức:

```bash
python manage.py process_videos --episode <id> --reencode
```

Chạy `python manage.py migrate` để tạo bảng công chiếu. Mở **Studio → Công chiếu** để chọn tập đã công khai/xử lý xong (tối thiểu 13 giây để tạo bộ đệm HLS), giờ bắt đầu và đối tượng Thường/VIP. Chỉ nhân viên đang hoạt động có quyền **Tổ chức và điều khiển công chiếu** (`cinema.manage_premieres`) mới được tạo, đổi lịch, chiếu ngay, kết thúc hoặc hủy; tài khoản VIP không có quyền phát sóng. Superuser có quyền này mặc định.

Trang `/premieres/` hiển thị lịch. Mỗi suất có đếm ngược, phát đồng bộ theo đồng hồ server và chat có kiểm duyệt/giới hạn tốc độ; không dùng mic hay giới hạn 3/10 ghế của phòng riêng. Nguồn phim công chiếu chỉ cấp ticket khi đang diễn ra và người xem đủ quyền. Manifest/segment được giới hạn theo phần đã chiếu; trình phát có độ trễ đệm khoảng 12 giây. Khi kết thúc tự nhiên, nguồn đang phát có thể nhận các đoạn cuối; hủy hoặc kết thúc thủ công dừng giao diện. Thao tác quản lý có phiên bản chống ghi đè và được ghi nhật ký admin.

Đây là **công chiếu video có sẵn**, chưa nhận luồng OBS/RTMP. Tập phim vẫn có quyền VOD độc lập: lên lịch công chiếu không tự khóa đường xem thông thường trước giờ chiếu và không phải cơ chế phát hành sớm độc quyền.

## Phụ đề và điều khiển trình phát

Chạy `python manage.py migrate` để áp dụng `0008_subtitle`. Trong admin → **Phụ đề** → Thêm, chọn tập phim, mã ngôn ngữ (`vi`, `en`, `en-US`…), tên hiển thị và file `.srt` hoặc `.vtt` mã hóa UTF-8. Hỗ trợ nhiều ngôn ngữ, mỗi ngôn ngữ một track trên mỗi tập. Khi sửa thông tin, bỏ trống file để giữ phụ đề hiện tại; upload file mới để thay nội dung. Quyền quản lý phụ đề được cấp riêng trong Django admin.

Giới hạn 2 MiB, 10.000 câu, tối đa 16.000 ký tự/câu. Mốc kết thúc phải sau bắt đầu và các câu theo thứ tự thời gian. SRT được đổi thành WebVTT; chỉ nhận văn bản thuần, bỏ cue settings/IDs và không hỗ trợ STYLE/REGION. Nội dung chuẩn hóa lưu trong database, không tạo file phụ đề public. Endpoint phụ đề yêu cầu cùng quyền xem phim (đăng nhập, tập ready, phim công khai và VIP khi cần), có `no-store` và `nosniff`.

Nút **CC / Phụ đề** luôn xuất hiện trên thanh điều khiển, kể cả tập chưa có track. Bảng phụ đề có lựa chọn ngôn ngữ/tắt, **Tạo phụ đề từ âm thanh** và **Dịch tự động**. Chọn phụ đề của mỗi người độc lập trên cả trang xem và phòng xem chung. [docs/examples/subtitles-demo.vi.srt](docs/examples/subtitles-demo.vi.srt) là file minh họa 20 giây dành cho clip màu tạo bằng `make_demo_video`, không phải bản dịch lời thoại phim.

Nút ±10 giây và phím ←/→ khi focus trong trình phát cập nhật vị trí ngay, giới hạn trong thời lượng/vùng có thể tua. Thao tác liên tiếp cộng dồn; lần làm mới nguồn HLS giữ vị trí vừa chọn. Phím mũi tên không can thiệp ô nhập/chọn ngôn ngữ. Trong phòng xem chung, chỉ chủ phòng được tua và điều khiển vị trí chung; khách vẫn chọn phụ đề/âm lượng riêng.

Mở **Xem chung** tại `/rooms/` để tạo phòng trước khi chọn phim. Tài khoản miễn phí mở phòng tối đa 3 người, VIP/staff mở phòng tối đa 10 người, tính cả chủ phòng. Giới hạn dựa trên gói của chủ phòng; VIP của người tham gia không tăng sức chứa phòng miễn phí. Khi VIP của chủ phòng hết hạn, phòng vẫn mở với 3 chỗ: chủ phòng và hai khách đang hiện diện tham gia sớm nhất giữ chỗ; những người còn lại rời phòng và có thể vào lại khi có chỗ trống. Không gian rạp hỗ trợ giao diện sáng/tối, màn chiếu lớn và lịch chiếu có thứ tự; màn chiếu luôn giữ nền tối. Chủ phòng dùng **Thêm phim** để chuẩn bị danh sách tối đa 50 tập, kéo thả hoặc dùng nút di chuyển để sắp xếp, rồi bấm **Phát** hoặc **Phát tiếp theo**. Nguồn mới bắt đầu từ đầu và chờ chủ phòng bấm phát trong trình chiếu. Đổi phim giữ nguyên liên kết mời, thành viên, tin nhắn và kết nối thoại. Có thể tạo nhanh phòng đã chọn sẵn từ trang xem phim.

Thành viên dùng **Gợi ý phim** và chỉ chủ phòng được duyệt thêm hoặc từ chối. Mỗi người có tối đa 5 đề xuất đang chờ, cả phòng tối đa 20. Thành viên không được sửa lịch chiếu hay điều khiển phim chung. Mọi thao tác quản lý kiểm tra phiên bản danh sách để tránh ghi đè thay đổi ở phiên khác. Mỗi người vẫn cần quyền xem riêng với phim VIP.

Khi tạo phòng, chủ phòng có thể đặt mật khẩu và bật **Duyệt người vào phòng**. **Cửa vào rạp** bên phải hàng ghế hiển thị số người chờ; chủ phòng bấm cửa để mở danh sách duyệt và cài đặt quyền vào phòng. Nếu bật cả hai, khách nhập đúng mật khẩu trước khi gửi yêu cầu, rồi bấm tham gia sau khi được duyệt. Đổi mật khẩu yêu cầu khách đang chờ hoặc đã được duyệt nhưng chưa vào phòng xác minh lại. Thành viên thiếu quyền xem phim VIP vẫn có thể trò chuyện trong phòng. Trình phát kiểm tra riêng quyền phim của từng người.

Vào phòng sẽ tự kết nối để nghe, microphone luôn tắt ban đầu. Bấm avatar của chính mình trên hàng ghế để bật hoặc tắt mic; chỉ thao tác này mới yêu cầu quyền microphone. Nếu trình duyệt chặn phát âm thanh, dùng **Bật âm thanh phòng** dưới hàng ghế. Chủ phòng có thể khóa mic từng thành viên từ avatar của họ. Khi được mở quyền nói, thành viên tự bấm avatar để bật lại mic. WebRTC truyền âm thanh giữa các trình duyệt. Trên máy chủ cần HTTPS và có thể cấu hình `ROOM_VOICE_ICE_SERVERS` theo mẫu trong `.env.example` để hỗ trợ các mạng cần STUN/TURN. Localhost có thể thử kết nối trực tiếp.

Thành viên trong phòng hiển thị trên 3 ghế miễn phí hoặc 10 ghế VIP, theo gói của chủ phòng, với tên hoặc avatar và giữ vị trí khi cập nhật hiện diện. Chủ phòng bấm avatar để khóa/cho phép bật mic, hoặc dùng nút **×** để loại thành viên. Viền sáng dùng mức âm thanh Web Audio của track thoại đang kết nối, tách biệt với trạng thái chỉ bật mic. Tắt mic hoặc bị khóa sẽ hiện biểu tượng mic gạch chéo. Không có Web Audio thì phòng vẫn hỗ trợ thoại và trạng thái mic, không mô phỏng hiệu ứng đang nói. **Phóng to rạp** mở toàn bộ không gian ở fullscreen; nút toàn màn hình trong video chỉ phóng trình phát.

Trò chuyện trực tiếp dùng avatar và tên công khai của người gửi, có dấu nhận biết chủ phòng, ô nhập cố định cùng bộ chọn emoji. Có thể thu gọn mà vẫn giữ bản nháp. Khi đang đọc tin cũ, tin mới hiện nút thông báo thay vì tự kéo xuống; bấm nút để trở về cuối cuộc trò chuyện. Tin nhắn là văn bản thuần, tối đa 500 ký tự, chỉ thành viên được vào phòng mới được đọc hoặc gửi.

## Phụ đề tự động và dịch local

Chạy `migrate` trước khi dùng phiên bản này để tạo bảng công việc dịch/nhận dạng. Hai tác vụ chạy ngoài web request; trình phát hiện trạng thái chờ, đang xử lý, hoàn tất hoặc lỗi. Worker giữ lại kết quả có cùng nguồn và phiên bản model, không tạo một bản dịch mới sau mỗi lần bấm. Endpoint tạo/xem kết quả đều kiểm tra quyền xem phim và CSRF cho thao tác POST.

- **Chưa có phụ đề:** trong CC, chọn ngôn ngữ lời thoại (tự nhận biết/Anh/Việt) rồi bấm **Tạo phụ đề tự động**. Server đọc file gốc trong `PRIVATE_MEDIA_ROOT`, nhận dạng thành phụ đề đúng mốc thời gian; khi có kết quả có thể chọn để xem hoặc dịch tiếp.
- **Đã có phụ đề gốc:** chọn track nguồn và ngôn ngữ đích rồi bấm **Dịch tự động**. Cấu hình local đóng gói hỗ trợ Anh ↔ Việt; bản dịch giữ các mốc thời gian. Nội dung từ nguồn thiếu lời thoại hoặc chỉ có nhạc không được tự coi là có câu dịch.
- Phụ đề được tạo/dịch bằng máy có thể nhận nhầm tên, bỏ sót lời nói hoặc dịch sai; tên track có nhãn tự động. Quản trị nên đối chiếu trước khi dùng làm bản phụ đề chính thức. Model `tiny` ưu tiên thử nghiệm CPU, không bảo đảm chất lượng của model lớn hoặc bản dịch do người kiểm duyệt.

Nhận dạng giữ track đã có cùng ngôn ngữ, kể cả bản do quản trị tải lên; không ghi đè khi đổi phiên bản model. Nếu muốn thay bằng kết quả nhận dạng mới, quản trị cần chủ động xóa track cũ, rồi tạo lại. Bản dịch tham chiếu nội dung track nguồn; sửa nguồn sẽ làm bản kết quả cũ hết hiệu lực.

Nhận dạng dùng [faster-whisper](https://github.com/SYSTRAN/faster-whisper#usage); dịch dùng model [Argos Translate](https://argos-translate.readthedocs.io/en/latest/source/examples.html) qua CTranslate2. Tách hai môi trường Python 3.12 khỏi `.venv` Django; không cài các model/dependencies lớn vào web runtime. `requirements-speech.txt` khóa `faster-whisper==1.2.1` và `av==18.1.0` vì PyAV 19 thay đổi đối số `metadata_errors` của `av.open`; tương thích này được theo dõi tại [faster-whisper #1495](https://github.com/SYSTRAN/faster-whisper/pull/1495).

Thiết lập lần đầu, ví dụ bằng `uv` (hoặc tạo venv/cài pip tương đương):

```bash
cd python_app
uv venv --python 3.12 .translation-venv
uv pip install --python .translation-venv/bin/python -r requirements-translation.txt
uv venv --python 3.12 .speech-venv
uv pip install --python .speech-venv/bin/python -r requirements-speech.txt
```

Trong `.env`, đặt `SPEECH_API_URL=http://127.0.0.1:5002`, `SPEECH_MODEL_VERSION=faster-whisper-tiny-v1`, `TRANSLATION_API_URL=http://127.0.0.1:5001`, `TRANSLATION_PROVIDER_VERSION=argos-en-vi-1.9` và `TRANSLATION_TARGETS=vi,en` như `.env.example`. Để trống URL tương ứng nếu muốn tắt một dịch vụ. Restart server web sau khi thay cấu hình; helper và web phải dùng cùng database, `PRIVATE_MEDIA_ROOT` và token nếu có.

Mở một terminal cho `./run-local.sh`, rồi trong terminal thứ hai chạy:

```bash
# Lần đầu: cho phép tải model nhận dạng và hai model dịch từ nguồn chính thức.
./run-caption-services.sh --download-models
# Những lần sau, khi model đã có:
./run-caption-services.sh
```

Helper dùng lại dịch vụ khỏe đã chạy ở cổng 5001/5002, khởi động phần còn thiếu và hai worker `process_translations --watch`, `process_transcriptions --watch`. `./run-caption-services.sh --check` chỉ kiểm tra môi trường/cấu hình/health. Ctrl+C dừng các tiến trình do lần chạy helper đó tạo, giữ dịch vụ có sẵn; log nằm trong thư mục bị Git ignore `reports/caption-services/`. Helper không mở trình phát, không tự tạo tài khoản và không khởi động lại web server. Nếu chạy worker thủ công, không cần đồng thời dùng thêm helper.

Model dịch nằm ở `.translation-data`, model lời thoại ở `.speech-models`; hai venv và các model không đưa vào Git. Lần tải model đầu cần Internet; khi đã cài, hai dịch vụ local xử lý văn bản/audio trên máy và không gửi nội dung phim ra dịch vụ ngoài. Service lời thoại chỉ chấp nhận file trong kho riêng tư, tối đa 3 giờ; bảo đảm file gốc vẫn còn. Đây là helper phát triển local, giữ các cổng loopback; triển khai dài hạn cần process manager, giới hạn tài nguyên và giám sát worker.

## Điểm IMDb

Migration `0009_movie_imdb` thêm **Mã phim IMDb**, **Điểm IMDb** và **Ngày đối chiếu điểm IMDb** vào Movie. Nhập ID dạng `tt1254207`, điểm 1,0–10,0 và ngày kiểm tra nguồn; có thể để trống khi chưa có dữ liệu. Không nhập ngày tương lai hoặc điểm thiếu ID. Liên kết đến IMDb được tạo cố định từ ID, không nhận URL tùy ý.

Điểm có nguồn được hiển thị trên card, hero, xem nhanh và trang chi tiết. Điểm IMDb dùng thang 10, tách với đánh giá Lumière thang 5; thiếu dữ liệu thì ẩn, không sinh điểm mẫu. Điểm hiện do quản trị cập nhật thủ công, không tự đồng bộ hoặc gọi API khi người dùng mở trang. Tham khảo [Ratings FAQ của IMDb](https://help.imdb.com/article/imdb/track-movies-tv/ratings-faq/G67Y87TFYYP6TWAV). Nếu tích hợp nguồn tự động cho dịch vụ thương mại, sử dụng nguồn được cấp phép phù hợp theo [hướng dẫn dữ liệu IMDb](https://help.imdb.com/article/imdb/track-movies-tv/can-i-use-your-ratings-on-my-website/GU66FTMF7DHVZBHZ).

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

Mỗi tài khoản chỉ có một browser session được cấp ticket hiện hành; nhiều tab dùng cùng session vẫn có thể hoạt động. Phát phim trong phòng xem chung yêu cầu mỗi người có quyền với phim đó. Muốn bảo vệ nội dung thương mại mạnh hơn cần DRM (Widevine/FairPlay/PlayReady), dịch vụ cấp license và quy trình xử lý nội dung phù hợp — chưa nằm trong bản này.

## Triển khai thực tế

- Dùng HTTPS, `DEBUG=0`, secret ngẫu nhiên tối thiểu 50 ký tự, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `PUBLIC_ORIGIN` đúng domain, MySQL và Redis riêng tư. Production bắt buộc có `REDIS_URL` để rate limit/phiên phát dùng chung giữa workers.
- Giữ Gunicorn chỉ lắng nghe loopback/private network. `TRUST_PROXY=1` và `TRUSTED_PROXY_IPS` chỉ khi reverse proxy tin cậy ghi đè `X-Forwarded-Proto`/`X-Real-IP`; chặn mọi truy cập trực tiếp tới Gunicorn.
- Cấu hình SMTP, backup MySQL và kho file, giám sát dung lượng/log worker. Không log query string của `/stream/` vì chứa ticket, không log secret/VNPay hash secret.
- `deploy/` có mẫu Nginx, systemd web service, video service và timer. Thay domain, TLS certificates, đường dẫn, UID/GID theo máy thật; không chạy nguyên mẫu mà chưa kiểm tra. Reverse proxy giới hạn request/upload trước Django; upload vẫn cần quota ổ đĩa.
- File `/etc/lumiere/env` chỉ cho service user đọc; secret không đặt trong Git. Kho private và kho public là hai thư mục khác nhau; quyền filesystem phải phù hợp với service và Nginx.
- Build Vue trước khi chạy `python manage.py collectstatic --noinput` để Django thu gom các tệp trong `static/bundles/catalog/`. Chạy `python manage.py check --deploy` và kiểm thử với `DEBUG=0` trước khi khởi động services. Giữ thư mục bundle cùng mã ứng dụng để Django đọc manifest.
- Chưa có kiểm toán bảo mật độc lập, đánh giá tải, DRM hay bài thử thanh toán thật. Cần kiểm tra thực tế MySQL, Redis, Nginx, storage/worker và VNPay trước khi mở cho người dùng.

Các tùy chọn bảo mật dựa trên [deployment checklist của Django](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/); luôn cập nhật bản vá dependencies và FFmpeg.

## Tường lửa ứng dụng (WAF)

Chạy `python manage.py migrate` rồi đăng nhập bằng tài khoản superuser. Mở **Studio → Bảo mật WAF** tại `/admin/security/` để xem cảnh báo, sự kiện hành vi, lượt giới hạn trong 24 giờ và trạng thái học của từng trang. Bấm mã định danh nguồn trong nhật ký để đối chiếu những sự kiện đã ghi của cùng nguồn.

| `WAF_MODE` trong `.env` | Hành vi |
| --- | --- |
| `monitor` (mặc định) | Ghi cảnh báo khi yêu cầu khớp quy tắc hoặc có dấu hiệu bất thường. Ghi cả những lần bị giới hạn POST. |
| `enforce` | Từ chối yêu cầu vi phạm quy tắc định dạng. Bật thêm giới hạn tạm thời cho truy cập ẩn danh khi nhiều tín hiệu hành vi được xác nhận. |
| `off` | Tắt quy tắc WAF và thu thập sự kiện. Giới hạn tần suất POST hiện có vẫn hoạt động. |

Khởi động lại Django sau khi đổi chế độ. Mô hình thống kê chạy cục bộ và học riêng cho `/browse/` và `/actors/` từ các truy vấn thành công trong sáu khung giờ đã kết thúc gần nhất. Mỗi nguồn đóng góp tối đa một mẫu cho mỗi trang trong một khung 10 phút. Khi đủ 50 mẫu, mô hình chấm các truy vấn lớn theo độ hiếm của độ dài, số trường và tổ hợp của hai tín hiệu. Điểm 0–100 giúp ưu tiên xem xét. Dashboard hiển thị **Đang thu thập mẫu** cho những trang chưa đủ dữ liệu.

Yêu cầu đã gắn cờ được giữ ngoài tập học. Điểm cao của một truy vấn là tín hiệu bổ sung khi WAF đối chiếu hoạt động từ cùng nguồn trong khoảng hai phút. Bộ phân tích đối chiếu các lần truy cập đường dẫn không khả dụng, từ chối quyền, đăng nhập thất bại và khớp quy tắc. Nhật ký cho thấy số lần xuất hiện của từng tín hiệu tại thời điểm tạo cảnh báo.

Trong chế độ `enforce`, chỉ khi nhiều nhóm hành vi độc lập ở ít nhất hai khu vực đạt ngưỡng, WAF mới trả `429` kèm `Retry-After` trong tối đa 90 giây đối với lượt đọc ẩn danh vào danh mục và trang công khai. Người đã đăng nhập, đăng nhập, quản trị, thanh toán, phát phim và phòng xem nằm ngoài phạm vi giới hạn này. Đặt `WAF_BEHAVIOR_MITIGATION=0` để giữ chặn theo quy tắc và chỉ theo dõi tương quan hành vi.

Nhật ký được lấy mẫu để giới hạn số lần ghi. Mỗi sự kiện lưu thời điểm, khu vực, phương thức, lý do, hành động và mã định danh nguồn đã băm có khóa. Cảnh báo lưu thêm điểm và tín hiệu tổng hợp. Mã định danh nhật ký thay đổi mỗi ngày. WAF không lưu địa chỉ IP gốc, URL, query string, token hoặc thông tin đăng nhập. Đặt lịch chạy `python manage.py prune_security_events` mỗi ngày để xóa sự kiện quá 30 ngày.

Phạm vi WAF là các yêu cầu đi đến Django. Giữ giới hạn lưu lượng và dung lượng tại reverse proxy để xử lý kết nối và tệp tĩnh trước khi ứng dụng nhận yêu cầu.

## Tìm kiếm và trạng thái nội dung

Tìm phim và diễn viên hỗ trợ chữ hoa tiếng Việt, không dấu và Unicode dạng tách dấu. Tìm phim bao gồm tên, mô tả và tên diễn viên được gắn với phim công khai. Dữ liệu chuẩn hóa được lưu trong database, tự cập nhật qua `save()`; migration `0004_normalized_search_fields` tạo dữ liệu cho các bản ghi cũ. Chạy `python manage.py migrate` trước khi khởi động phiên bản này.

`QuerySet.update()`, `bulk_create()`, `bulk_update()` và SQL trực tiếp không gọi `save()`. Nếu import/sửa tên hoặc mô tả bằng các cách đó, cập nhật cả trường tìm kiếm hoặc chạy lại khi không có thao tác chỉnh sửa nội dung đồng thời:

```bash
python manage.py reindex_search
```

Lệnh chạy theo batch, hỗ trợ `--database` và `--batch-size`. Truy vấn chuỗi con hiện vẫn quét dữ liệu ở database; các trường chuẩn hóa chưa thay thế full-text search cho thư viện lớn.

Danh mục có bộ lọc năm, kết hợp với các bộ lọc khác và giữ năm khi phân trang/đổi thể loại/quốc gia. Phim chưa có tập `ready` hiển thị “Đang chuẩn bị”; xem nhanh không tạo liên kết phát cho phim đó. Hero trang khám phá chỉ chọn phim có tập sẵn sàng. Quyền VIP/đăng nhập tiếp tục được kiểm tra tại server.

## Giao diện và thành viên VIP

Header có tìm kiếm tức thì bằng Vue/TypeScript: nhập từ 2 ký tự, tìm tiếng Việt có/không dấu, nhận tối đa 6 phim và 3 diễn viên công khai. Hỗ trợ phím lên/xuống, Enter, Escape, tìm kiếm trên điện thoại và biểu mẫu dự phòng khi JavaScript không hoạt động. API không trả về phim nháp, nguồn phát hoặc lịch sử cá nhân.

**Tủ phim** có tìm kiếm, sắp xếp, phân trang và bộ lọc Chưa xem/Đang xem/Đã xem/Đang chuẩn bị. Một phim chỉ được coi là đã xem khi mọi tập đang sẵn sàng đều đạt mốc kết thúc; tập chưa biết thời lượng không được suy đoán là đã hoàn thành. Chọn nhiều phim hoặc cả trang rồi xóa khỏi tủ; lịch sử xem được giữ lại. Endpoint POST chỉ tác động tủ của tài khoản đang đăng nhập, có CSRF và giới hạn 100 mã phim mỗi lần.

Kệ **Dành cho bạn** dựa trên phim của chính bạn đã lưu, xem hoặc chấm từ 4/5. Thể loại được ưu tiên trước diễn viên/quốc gia; từng thẻ giải thích mối liên hệ thực. Phim nháp, phim chưa có bản xem, phim đã xem hết và phim bị chấm thấp không được gợi ý. Lịch sử đã ẩn khỏi Xem tiếp không làm nguồn sở thích; khi chưa đủ dữ liệu, kệ cá nhân không xuất hiện. Không gọi dịch vụ AI bên ngoài hoặc tạo điểm phù hợp giả.

**Studio** có báo cáo 7/30/90 ngày theo múi giờ ứng dụng: chỉ cộng đơn đã thanh toán có `paid_at`, có so sánh kỳ trước, biểu đồ và bảng số liệu theo ngày. Tổng quan toàn thời gian vẫn được ghi riêng. Các kiểm tra phim công khai chưa có bản xem, chưa tải poster riêng, tập thiếu phụ đề và bản nháp đã có video dẫn đến đúng bộ lọc quản trị. Số liệu doanh thu, thành viên và nội dung tuân theo quyền model của nhân viên.

Nút mặt trời/mặt trăng trên header chuyển giữa giao diện sáng và tối. Lựa chọn được lưu trong localStorage của trình duyệt (`lumiere-theme`), áp dụng trước khi tải stylesheet và giữ khi đổi trang/tải lại. Mặc định giữ giao diện tối; nếu trình duyệt chặn lưu trữ, nút vẫn đổi giao diện cho trang hiện tại. Hero/ảnh phim và trình phát giữ bảng màu tối để bảo đảm tương phản; không dùng bộ lọc đảo màu lên nội dung phim.

Thành viên còn hạn VIP mở `/vip/` sẽ thấy quyền lợi/hạn dùng và các lối vào phim VIP, xem chung, tủ phim. Bảng giá chỉ xuất hiện khi chủ động mở liên kết Gia hạn (`/vip/?renew=1`). Khách, tài khoản thường và gói hết hạn vẫn có luồng mua. Tham số `renew` không cấp VIP; quyền vẫn chỉ được thay đổi bởi xác nhận thanh toán hợp lệ hoặc quản trị.

Có thể mua VIP Năm khi đang dùng VIP Tháng. Sau IPN thành công, backend khóa đơn và tài khoản, lưu kỳ sử dụng mới từ thời điểm muộn hơn giữa lúc xác nhận và hạn VIP hiện có, rồi cộng đủ số ngày đã mua. Gói mới hiển thị **Chờ kích hoạt · Đã thanh toán** và tự chuyển thành **Đang sử dụng** khi kỳ trước kết thúc; không cần cron, thanh toán lại hoặc thao tác kích hoạt. Nếu mua nhiều gói trước, chúng tiếp nối theo thứ tự xác nhận thanh toán. Các gói tháng/năm có cùng quyền lợi, khác thời hạn.

Migration `0024_order_vip_periods` bổ sung ngày bắt đầu/kết thúc và tên gói khi mua. Giá, số ngày và tên gói được lưu theo đơn; sửa danh mục gói không đổi kỳ đã mua. Trang gia hạn hiển thị ngày dự kiến theo lựa chọn; ngày chính xác chỉ chốt khi IPN hợp lệ. Callback lặp, sai chữ ký/số tiền hoặc thanh toán thất bại không cấp thêm kỳ. Hồ sơ và quản trị hiển thị kỳ sử dụng để đối soát. Đơn cũ chưa lưu ngày kỳ vẫn giữ nguyên và không suy đoán lịch sử từ hạn VIP hiện tại. Kiểm thử logic: `python manage.py test cinema.test_vip_renewal_queue`.

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
# Kiểm tra tương tác tua, làm mới nguồn và xem nhanh bằng Node (nếu đã cài).
node --test tests/*.test.cjs
```

Bộ test kiểm tra quyền video/phụ đề, chữ ký/phiên/hạn token, VIP hết hạn, CSRF, XSS escaping, quyền điều khiển phòng, giới hạn phòng, callback VNPay, dữ liệu nhập, trailer/upload/URL, điểm IMDb và bộ lọc nội dung. Local UI/video cần thêm kiểm tra trình duyệt với file thật; test tổng hợp không chứng minh chống tải tuyệt đối.
