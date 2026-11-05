import json
import shutil
import subprocess
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from cinema.models import Episode

class Command(BaseCommand):
    help = 'Xử lý các video pending thành HLS. Chạy định kỳ trong worker riêng, không chạy trong request.'
    def add_arguments(self, parser):
        parser.add_argument('--episode', type=int)
        parser.add_argument('--retry-failed', action='store_true')
    def handle(self, *args, **options):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'): raise CommandError('Cần cài FFmpeg và ffprobe.')
        query = Episode.objects.all()
        if options['episode']: query = query.filter(pk=options['episode'])
        if options['retry_failed']: query.filter(status='failed').update(status='pending', error='')
        for episode in query.filter(status='pending'):
            if not Episode.objects.filter(pk=episode.pk, status='pending').update(status='processing'): continue
            output = settings.PRIVATE_MEDIA_ROOT / 'hls' / str(episode.asset_id)
            try:
                source = episode.source.path
                probe = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,matroska,webm', '-show_format', '-show_streams', '-of', 'json', source], capture_output=True, text=True, check=True, timeout=60)
                metadata = json.loads(probe.stdout)
                if not any(s.get('codec_type') == 'video' for s in metadata.get('streams', [])): raise ValueError('File không có luồng video.')
                duration = float(metadata['format']['duration'])
                if not 0 < duration <= 6 * 3600: raise ValueError('Thời lượng video không hợp lệ hoặc quá 6 giờ.')
                output.mkdir(parents=True, exist_ok=True, mode=0o700)
                subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,matroska,webm', '-i', source, '-map', '0:v:0', '-map', '0:a:0?', '-map_metadata', '-1', '-vf', "scale=w='min(1280,iw)':h=-2", '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-threads', '2', '-c:a', 'aac', '-b:a', '128k', '-force_key_frames', 'expr:gte(t,n_forced*6)', '-f', 'hls', '-hls_time', '6', '-hls_playlist_type', 'vod', '-hls_segment_filename', str(output / 'seg%05d.ts'), str(output / 'index.m3u8')], capture_output=True, check=True, timeout=6 * 3600)
                Episode.objects.filter(pk=episode.pk).update(status='ready', duration=duration, error='')
                self.stdout.write(self.style.SUCCESS(f'Episode {episode.pk}: ready'))
            except Exception as exc:
                shutil.rmtree(output, ignore_errors=True)
                Episode.objects.filter(pk=episode.pk).update(status='failed', error=f'{type(exc).__name__}: kiểm tra định dạng video và log worker.')
                self.stderr.write(f'Episode {episode.pk}: {type(exc).__name__}')
