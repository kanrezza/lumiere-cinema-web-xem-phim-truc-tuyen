from django.core.management.base import BaseCommand
from cinema.models import Category, Movie, Plan

class Command(BaseCommand):
    help = 'Tạo phim minh họa và gói VIP; không tạo tài khoản/mật khẩu mặc định.'
    def handle(self, *args, **options):
        science, _ = Category.objects.get_or_create(slug='vien-tuong', defaults={'name':'Viễn tưởng'})
        drama, _ = Category.objects.get_or_create(slug='tam-ly', defaults={'name':'Tâm lý'})
        adventure, _ = Category.objects.get_or_create(slug='phieu-luu', defaults={'name':'Phiêu lưu'})
        data = [('Chạm vào vô tận','orbit',science,True), ('Sau hoàng hôn','dusk',drama,False), ('Khu rừng thì thầm','forest',adventure,False), ('Thành phố không ngủ','city',drama,True), ('Phía bên kia đại dương','ocean',adventure,True), ('Mùa hè năm ấy','summer',drama,False)]
        for title, slug, category, vip in reversed(data):
            movie, _ = Movie.objects.get_or_create(slug=slug, defaults={'title':title, 'artwork':slug, 'description':f'{title} — Một hành trình khám phá những điều chưa biết, nơi những cuộc gặp gỡ nhỏ bé có thể thay đổi cả một cuộc đời. Đây là phim minh họa cho giao diện Lumière; quản trị viên cần upload nội dung được phép sử dụng trước khi phát.', 'is_vip':vip, 'published':True, 'kind':'series' if slug == 'city' else 'movie'})
            movie.categories.add(category)
        Plan.objects.get_or_create(name='VIP Tháng', defaults={'price':59000, 'days':30})
        Plan.objects.get_or_create(name='VIP Năm', defaults={'price':599000, 'days':365})
        self.stdout.write(self.style.SUCCESS('Đã tạo dữ liệu minh họa. Giá gói là giá mẫu, có thể sửa trong admin.'))
