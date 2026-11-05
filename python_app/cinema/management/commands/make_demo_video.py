"""Generate a short synthetic clip to exercise uploads/playback without copyrighted films."""
import subprocess
import tempfile
from pathlib import Path
from django.conf import settings
from django.core.files import File
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from cinema.models import Movie, Episode

class Command(BaseCommand):
    help = 'Tạo clip kiểm tra 20 giây cho phim minh họa Sau hoàng hôn (local DEBUG only).'
    def handle(self, *args, **options):
        if not settings.DEBUG: raise CommandError('Demo generation is disabled outside DEBUG.')
        call_command('seed_demo')
        movie = Movie.objects.get(slug='dusk')
        episode, _ = Episode.objects.get_or_create(movie=movie, number=1, defaults={'title':'Clip kiểm tra trình phát · 20 giây'})
        if episode.source:
            self.stdout.write('Tập đã có nguồn; không ghi đè file hiện tại.')
            return
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'demo.mp4'
            subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=24', '-t', '20', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-threads', '2', str(path)], check=True, timeout=60)
            with path.open('rb') as handle: episode.source.save('demo.mp4', File(handle))
        call_command('process_videos', episode=episode.pk)
        self.stdout.write(self.style.SUCCESS(f'Clip minh họa: /watch/{episode.pk}/ (cần đăng nhập).'))
