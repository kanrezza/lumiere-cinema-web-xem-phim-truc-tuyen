from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cinema.models import Category, Movie


class Command(BaseCommand):
    help = 'Thêm đoạn giới thiệu Big Buck Bunny có ghi công từ clip demo được đóng gói, không tải phim đầy đủ.'

    @transaction.atomic
    def handle(self, *args, **options):
        clip = Path(settings.BASE_DIR) / 'static' / 'imagery' / 'big-buck-bunny-preview.mp4'
        if not clip.is_file():
            raise CommandError('Không tìm thấy clip giới thiệu Big Buck Bunny được đóng gói trong static/imagery.')
        movie, _ = Movie.objects.get_or_create(slug='big-buck-bunny', defaults={
            'title': 'Big Buck Bunny', 'year': 2008, 'country': 'Hà Lan', 'published': True,
            'artwork': 'big-buck-bunny-backdrop',
            'description': 'Một chú thỏ hiền lành và cuộc đối đầu với ba kẻ quậy phá trong khu rừng. '
                           'Phim hoạt hình ngắn không lời của Blender Foundation (2008). '
                           'Nguồn: https://peach.blender.org/ · Giấy phép CC BY 3.0: '
                           'https://creativecommons.org/licenses/by/3.0/',
        })
        if movie.has_trailer:
            self.stdout.write('Big Buck Bunny đã có trailer; giữ nguyên nội dung hiện tại.')
            return
        with clip.open('rb') as handle:
            movie.trailer_file = File(handle, name='big-buck-bunny-intro.mp4')
            movie.trailer_credit = (
                'Đoạn giới thiệu thử nghiệm 16 giây, trích/cắt từ Big Buck Bunny. '
                '© 2008 Blender Foundation · https://peach.blender.org/ · '
                'CC BY 3.0: https://creativecommons.org/licenses/by/3.0/ '
                'Đây là đoạn trích demo, không phải trailer chính thức.'
            )
            movie.full_clean()
            movie.save(update_fields=['trailer_file', 'trailer_credit'])
        category, _ = Category.objects.get_or_create(slug='hoat-hinh', defaults={'name': 'Hoạt hình'})
        movie.categories.add(category)
        self.stdout.write(self.style.SUCCESS('Đã thêm đoạn giới thiệu Big Buck Bunny. Không tạo tập phim hoặc thay đổi quyền xem.'))
