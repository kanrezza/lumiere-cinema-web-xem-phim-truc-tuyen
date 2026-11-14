"""Build an original two-episode series for local playback checks."""

import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from cinema.models import Episode, Movie, Subtitle
from cinema.subtitles import normalize_subtitle


SERIES_SLUG = 'tram-anh-sang-demo'
SERIES_TITLE = 'Trạm ánh sáng (Demo)'
CLIPS = (
    (
        'Tín hiệu màu hổ phách',
        '0x101528:0xD47A39:0x423955',
        'Trạm nhận tín hiệu đầu tiên.',
        'The station receives its first signal.',
    ),
    (
        'Hồi âm màu lam',
        '0x10182E:0x369EA9:0x2C4D91',
        'Tín hiệu thứ hai xác nhận kết nối.',
        'The second signal confirms the connection.',
    ),
)


def run_ffmpeg(*args):
    try:
        subprocess.run(
            ['ffmpeg', '-nostdin', '-y', '-v', 'error', *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip()
        raise CommandError(f'FFmpeg không tạo được clip minh họa. {detail}') from error
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CommandError(f'Không chạy được FFmpeg. {error}') from error


def make_clip(path, palette, number):
    first, second, third = palette.split(':')
    gradient = (
        f'gradients=size=640x360:rate=24:c0={first}:c1={second}:c2={third}'
        f':nb_colors=3:type=radial:seed={number}:speed=0.04'
    )
    run_ffmpeg(
        '-f', 'lavfi', '-i', gradient, '-t', '30',
        '-vf', 'drawgrid=w=80:h=60:t=1:c=white@0.12',
        '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-threads', '2', str(path),
    )


def save_missing_file(instance, field_name, path, **updates):
    field = getattr(instance, field_name)
    with path.open('rb') as handle:
        field.save(path.name, File(handle), save=False)
    try:
        saved = type(instance).objects.filter(
            pk=instance.pk, **{field_name: ''},
        ).update(**{field_name: field.name, **updates})
    except Exception:
        field.delete(save=False)
        raise
    if not saved:
        field.delete(save=False)
    instance.refresh_from_db()


def add_demo_captions(episode, vietnamese, english):
    cues = (
        ('vi', 'Tiếng Việt', vietnamese, 'Phụ đề mẫu dùng để kiểm tra đổi tập.'),
        ('en', 'English', english, 'Sample captions for testing episode changes.'),
    )
    for language, label, opening, ending in cues:
        text = (
            f'WEBVTT\n\n00:00:03.000 --> 00:00:13.000\n{opening}\n\n'
            f'00:00:20.000 --> 00:00:29.500\n{ending}\n'
        )
        Subtitle.objects.get_or_create(
            episode=episode,
            language=language,
            defaults={'label': label, 'content': normalize_subtitle(ContentFile(text.encode(), name='demo.vtt'))},
        )


class Command(BaseCommand):
    help = 'Tạo bộ phim demo hai tập 30 giây với phụ đề Việt/Anh trên máy local (DEBUG).'

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Chỉ tạo phim minh họa khi DEBUG=1.')
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            raise CommandError('Cần cài FFmpeg và ffprobe.')

        movie, _ = Movie.objects.get_or_create(
            slug=SERIES_SLUG,
            defaults={
                'title': SERIES_TITLE,
                'kind': 'series',
                'artwork': 'orbit',
                'description': (
                    'Hai đoạn phim màu chuyển động tự tạo bằng FFmpeg, mỗi tập 30 giây. '
                    'Phụ đề Việt và Anh dùng để kiểm tra xem tiếp và chuyển tập.'
                ),
            },
        )
        if movie.title != SERIES_TITLE or movie.kind != 'series':
            raise CommandError('Đường dẫn dành cho bộ phim demo đang được dùng bởi nội dung khác.')

        episode_urls = []
        with TemporaryDirectory(prefix='lumiere-demo-') as folder:
            temporary = Path(folder)
            for number, (title, palette, vietnamese, english) in enumerate(CLIPS, start=1):
                episode, _ = Episode.objects.get_or_create(
                    movie=movie, number=number, defaults={'title': title},
                )
                if episode.title != title:
                    raise CommandError(f'Tập {number} đã được chỉnh sửa. Giữ nguyên nội dung hiện tại.')
                if not episode.source:
                    path = temporary / f'demo-{number}.mp4'
                    make_clip(path, palette, number)
                    save_missing_file(episode, 'source', path, status='pending', duration=0, error='')
                if episode.status in ('pending', 'failed'):
                    call_command('process_videos', episode=episode.pk, retry_failed=True, stdout=self.stdout, stderr=self.stderr)
                    episode.refresh_from_db()
                playlist = settings.PRIVATE_MEDIA_ROOT / 'hls' / str(episode.asset_id) / 'index.m3u8'
                if episode.status != 'ready' or episode.duration <= 0 or not playlist.is_file():
                    raise CommandError(f'Tập {number} chưa có HLS sẵn sàng. Kiểm tra tập {episode.pk} trong Studio.')
                add_demo_captions(episode, vietnamese, english)
                episode_urls.append(reverse('watch', args=[episode.pk]))
                if number == 1 and not movie.backdrop:
                    backdrop = temporary / f'{SERIES_SLUG}.jpg'
                    run_ffmpeg('-ss', '12', '-i', episode.source.path, '-frames:v', '1', str(backdrop))
                    save_missing_file(movie, 'backdrop', backdrop)

        Movie.objects.filter(pk=movie.pk, published=False).update(published=True)
        details = reverse('movie', args=[movie.slug])
        self.stdout.write(self.style.SUCCESS(f'{SERIES_TITLE}: {details}'))
        for number, url in enumerate(episode_urls, start=1):
            self.stdout.write(f'Tập {number}: {url}')
