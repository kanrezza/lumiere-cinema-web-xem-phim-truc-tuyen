# Sao lưu và phục hồi Lumière

Một snapshot chứa database, ảnh và tệp đính kèm công khai, video gốc và các đoạn HLS riêng tư. Lệnh tạo manifest SHA-256 sau khi chép xong. Lệnh phục hồi kiểm tra kích thước và SHA-256 của từng file trước khi bàn giao thư mục mới. Với SQLite, cả hai lệnh cũng chạy `PRAGMA quick_check`.

## Tạo snapshot

Chọn thời điểm bảo trì và tạm dừng các tiến trình có thể ghi database hoặc media, gồm web, worker chuyển mã, xử lý phụ đề và tác vụ dọn dữ liệu. Database và media được sao chép theo thứ tự. Khoảng tạm dừng này giữ các bản ghi và file tham chiếu cùng một thời điểm.

Từ `python_app`, kích hoạt `.venv`, nạp biến môi trường của bản cài đặt, rồi chạy:

```bash
python manage.py backup_lumiere "/mnt/lumiere-backups/snapshot-$(date -u +%Y%m%d-%H%M%S)"
```

Thư mục cha trong ví dụ cần tồn tại. Snapshot chỉ dùng được khi `manifest.json` đã xuất hiện và lệnh kết thúc thành công. Giữ ít nhất một bản ở ổ hoặc nơi lưu trữ độc lập với máy ứng dụng, giới hạn quyền đọc và mã hóa nơi lưu vì bản sao chứa dữ liệu tài khoản và video riêng tư. Quản lý cấu hình `.env` và khóa bí mật bằng kênh riêng. Ghi lại phiên bản ứng dụng đang chạy để có thể khôi phục với schema tương ứng.

SQLite sử dụng API snapshot, gồm cả giao dịch đã commit trong WAL. MySQL cần `mysqldump` của MySQL 8 và quyền đọc dữ liệu. Schema của ứng dụng dùng InnoDB để dump có thể dùng giao dịch nhất quán.

## Phục hồi SQLite trong thư mục trống

```bash
python manage.py restore_lumiere /mnt/lumiere-backups/snapshot-20261117-010000 /tmp/lumiere-recovery-copy
```

Đích là một thư mục mới bên ngoài snapshot. Sau khi lệnh thành công, thư mục chứa `db.sqlite3`, `public_media/` và `private_media/`. Lệnh từ chối đích đã tồn tại để giữ nguyên dữ liệu ở đó.

Để thử bản phục hồi qua web chỉ trên máy cục bộ, dùng phiên bản mã tương ứng với snapshot và đã build frontend. Chạy từ `python_app`:

```bash
DEBUG=1 DB_NAME= REDIS_URL= TRUST_PROXY=0 \
  LUMIERE_RECOVERY_ROOT=/tmp/lumiere-recovery-copy \
  python manage.py runserver 127.0.0.1:8090 --settings=config.recovery
```

Mở `http://127.0.0.1:8090/`, kiểm tra danh mục, đăng nhập, lịch sử giao dịch và mở một phim. Cấu hình `config.recovery` cô lập SQLite cùng kho media và vô hiệu hóa gửi email, VNPay, tạo phụ đề tự động và dịch vụ chuyển tiếp thoại bên ngoài. Địa chỉ bind chỉ dùng để diễn tập local.

## Phục hồi MySQL vào môi trường riêng

Sau `restore_lumiere`, snapshot MySQL xuất `database.sql` đã xác minh và hai kho media. Dùng thông tin đăng nhập được cấp riêng cho máy phục hồi, hỗ trợ lưu qua `mysql_config_editor` với tên profile `lumiere-recovery`. Tạo tên database mới để phép nhập chỉ bắt đầu khi đích được tạo thành công:

```bash
mysql --login-path=lumiere-recovery -e 'CREATE DATABASE lumiere_recovery CHARACTER SET utf8mb4' &&
  mysql --login-path=lumiere-recovery lumiere_recovery < /tmp/lumiere-recovery-copy/database.sql
```

Chạy Lumière ở bản cài đặt riêng, trỏ `DB_*` đến database mới và đặt hai kho media đã phục hồi ở đường dẫn tương ứng với cấu hình môi trường. Với [stack staging](STAGING.md), các đường dẫn trong container là `/app/public_media` và `/app/private_media`. Cô lập cache, thông tin thanh toán và email với production khi chạy thử.

Trước khi đưa dữ liệu phục hồi trở lại phục vụ, đối chiếu các yêu cầu xóa hoặc ẩn danh đã xử lý sau ngày tạo snapshot và áp dụng lại các thay đổi cần thiết. Bước này ngăn dữ liệu đã xóa hoặc ẩn danh xuất hiện lại từ snapshot cũ.

## Diễn tập tự động bằng dữ liệu mẫu

Sau khi cài FFmpeg, ffprobe và build frontend, chạy từ `python_app`:

```bash
DEBUG=1 DB_NAME= REDIS_URL= python manage.py drill_lumiere_restore
```

Lệnh tạo database SQLite và phim mẫu HLS trong thư mục tạm, sao lưu rồi phục hồi sang thư mục mới. Sau khi làm cho đường dẫn dữ liệu nguồn không còn khả dụng, lệnh mở trang xem bằng tài khoản đã phục hồi, xác nhận đơn mẫu, ảnh bìa và phụ đề, tải playlist và các đoạn HLS có xác thực qua Django, rồi yêu cầu FFmpeg giải mã video. Thư mục tạm được dọn sau khi hoàn thành. Giữ kết quả diễn tập định kỳ để phát hiện sớm lỗi phục hồi.
