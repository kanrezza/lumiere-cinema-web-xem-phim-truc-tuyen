"""Exercise restored fixtures through the existing playback routes."""
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from .models import Episode, Order, Plan, User


FIXTURE_USERNAME = 'recovery-viewer'
FIXTURE_PASSWORD = 'Local-recovery-fixture-only-253'


def create_fixtures():
    viewer = User.objects.create_user(
        username=FIXTURE_USERNAME, email='recovery@example.invalid', password=FIXTURE_PASSWORD,
    )
    plan = Plan.objects.create(name='Gói dùng để kiểm thử phục hồi', price=1000, days=30)
    Order.objects.create(user=viewer, plan=plan, amount=plan.price, days=plan.days, status='paid', paid_at=timezone.now())


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def exported_hls(client, episode, directory):
    ticket = client.post(reverse('ticket', args=[episode.pk]), HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
    require(ticket.status_code == 200, 'Không cấp được vé phát cho tài khoản đã khôi phục.')
    playlist = client.get(ticket.json()['url'])
    require(playlist.status_code == 200, 'Không tải được playlist HLS đã khôi phục.')
    lines = playlist.content.decode('utf-8').splitlines()
    require(lines and lines[0] == '#EXTM3U' and '#EXT-X-ENDLIST' in lines, 'Danh sách phát đã khôi phục chưa hoàn chỉnh.')

    segment_count = 0
    for index, line in enumerate(lines):
        if not line or line.startswith('#'):
            continue
        segment_name = Path(urlsplit(line).path).name
        require(re.fullmatch(r'seg\d{5,}\.ts', segment_name), 'Danh sách phát chứa tên đoạn HLS không hợp lệ.')
        response = client.get(line)
        try:
            require(response.status_code == 200 and response.streaming, 'Không tải được đoạn HLS đã khôi phục.')
            with (directory / segment_name).open('xb') as segment:
                for chunk in response.streaming_content:
                    segment.write(chunk)
        finally:
            response.close()
        lines[index] = segment_name
        segment_count += 1

    require(segment_count > 0, 'Danh sách phát thiếu các đoạn phim.')
    local_playlist = directory / 'index.m3u8'
    local_playlist.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return local_playlist, segment_count


def verify_fixtures():
    viewer = User.objects.get(username=FIXTURE_USERNAME)
    order = Order.objects.get(user=viewer, status='paid')
    require(order.amount == 1000 and order.days == 30, 'Thông tin đơn không khớp dữ liệu đã sao lưu.')
    episode = Episode.objects.select_related('movie').get(
        movie__slug='tram-anh-sang-demo', movie__published=True, status='ready', number=1,
    )
    require(Path(episode.source.path).is_file(), 'Thiếu video gốc đã khôi phục.')

    client = Client(HTTP_HOST='testserver', enforce_csrf_checks=True)
    login = reverse('login')
    require(client.get(login).status_code == 200, 'Không mở được biểu mẫu đăng nhập.')
    login_response = client.post(
        login, {'username': FIXTURE_USERNAME, 'password': FIXTURE_PASSWORD},
        HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value,
    )
    require(login_response.status_code == 302, 'Thông tin đăng nhập của tài khoản đã khôi phục không hợp lệ.')
    response = client.get(reverse('watch', args=[episode.pk]))
    require(response.status_code == 200, 'Trang phát phim không mở được sau phục hồi.')

    subtitle = episode.subtitles.get(language='vi')
    response = client.get(reverse('subtitle', args=[episode.pk, subtitle.pk]))
    require(response.status_code == 200 and response.content.startswith(b'WEBVTT'), 'Không phục hồi được phụ đề.')
    picture = settings.MEDIA_ROOT / episode.movie.backdrop.name
    require(picture.is_file() and picture.stat().st_size > 0, 'Không phục hồi được ảnh bìa công khai.')
    response = client.get(episode.movie.backdrop.url)
    try:
        require(response.status_code == 200 and response['Content-Type'] == 'image/jpeg', 'Ảnh bìa phục hồi không tải được.')
    finally:
        response.close()

    with TemporaryDirectory(prefix='lumiere-restored-hls-') as media:
        local_playlist, segments = exported_hls(client, episode, Path(media))
        decoded = subprocess.run(
            ['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(local_playlist),
             '-map', '0:v:0', '-progress', 'pipe:1', '-f', 'null', '-'],
            capture_output=True, text=True, check=True, timeout=90,
        )
        frame_counts = re.findall(r'^frame=(\d+)$', decoded.stdout, re.MULTILINE)
        require(frame_counts and int(frame_counts[-1]) > 0, 'FFmpeg không giải mã được khung hình đã phục hồi.')
    print(f'Đã xác minh tài khoản, đơn đã thanh toán, phụ đề, ảnh bìa và video gốc. '
          f'FFmpeg giải mã {frame_counts[-1]} khung hình từ {segments} đoạn HLS qua luồng phát đã xác thực.')
