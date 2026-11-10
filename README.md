# Hệ Thống Quản Lý Phim Online (Lumière)


Hệ thống cho phép người dùng xem và khám phá phim trực tuyến, đồng thời cung cấp bộ công cụ quản trị toàn diện cho Admin.

---

## Tính năng chính

### Cho người dùng (User)

- **Khám phá phim:** Xem danh sách phim theo thể loại, phim bộ, phim lẻ, phim chiếu rạp.
- **Tìm kiếm:** Tìm kiếm phim theo tên, thể loại hoặc quốc gia.
- **Đánh giá:** Chấm điểm và xem bảng xếp hạng phim đánh giá cao nhất.
- **Bình luận:** Để lại bình luận và tương tác với cộng đồng.
- **Yêu thích:** Lưu phim vào danh sách yêu thích cá nhân.
- **Lịch sử xem:** Theo dõi lại các phim đã xem.
- **Diễn viên:** Xem danh sách diễn viên và các phim họ tham gia.

### Cho quản trị viên (Admin)

- **Quản lý phim:** Thêm, sửa, xóa phim và tập phim.
- **Quản lý người dùng:** Khóa/mở khóa tài khoản, phân quyền.
- **Quản lý đánh giá:** Xem và xóa các đánh giá không phù hợp.

---

## Công nghệ sử dụng

- **Framework:** Laravel 12
- **Language:** PHP, Blade Template
- **Database:** MySQL
- **Server:** XAMPP (Apache + MySQL)
- **Frontend:** HTML, CSS, JavaScript (không dùng framework)

---

## Khởi tạo quản trị cho bản Laravel

Không có tài khoản hoặc mật khẩu quản trị mặc định. Để chạy `AdminUserSeeder`, đặt `ADMIN_EMAIL` hợp lệ và `ADMIN_PASSWORD` tối thiểu 12 ký tự trong môi trường riêng; không đưa giá trị thật lên Git. Nếu thiếu hoặc không hợp lệ, seeder cảnh báo rồi bỏ qua việc tạo quản trị. Nếu đã cache cấu hình Laravel, cập nhật cache sau khi đổi các biến này. Chạy lại seeder sẽ cập nhật mật khẩu và quyền của tài khoản có email đã cấu hình; chỉ thực hiện khi bạn chủ động muốn cập nhật tài khoản đó.

---

## Hướng dẫn cài đặt

1. Clone project về máy:

```bash
git clone https://github.com/kanrezza/he-thong-quan-ly-phim-online.git
cd he-thong-quan-ly-phim-online
```

2. Cài đặt dependencies:

```bash
composer install
```

3. Tạo file môi trường:

```bash
cp .env.example .env
php artisan key:generate
```

4. Cấu hình database trong file `.env`:

```env
DB_DATABASE=tên_database_của_bạn
DB_USERNAME=root
DB_PASSWORD=
```

5. Import database:
   - Mở **phpMyAdmin**, tạo database mới
   - Import file `database/sql/lumiere.sql`

6. Tạo symbolic link cho storage:

```bash
php artisan storage:link
```

7. Chạy ứng dụng (dùng XAMPP hoặc):

```bash
php artisan serve
```

---

## Cấu trúc thư mục

- `app/Http/Controllers/` — Xử lý logic chính
- `app/Models/` — Các model tương tác database
- `resources/views/` — Giao diện Blade (movies, admin, actors, auth...)
- `database/migrations/` — Cấu trúc bảng database
- `database/sql/` — File SQL dump để import dữ liệu mẫu
- `routes/web.php` — Định nghĩa toàn bộ routes
- `public/` — Assets công khai
- `storage/app/public/posters/` — Ảnh poster phim

---

## Thành viên phát triển

- **Trần Đình Danh** · Phenikaa University
