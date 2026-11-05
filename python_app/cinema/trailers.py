"""Public marketing trailers are separate from private episode originals."""
import json
import math
import re
import subprocess
import tempfile
from contextlib import suppress
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from django.core.exceptions import ValidationError

MAX_TRAILER_BYTES = 50 * 1024 * 1024
MAX_TRAILER_SECONDS = 300
_VIDEO_ID = re.compile(r'[A-Za-z0-9_-]{11}')


def youtube_embed_url(value):
    """Return a canonical embed URL, never arbitrary HTML or a caller's query."""
    if not isinstance(value, str):
        return ''
    value = value.strip()
    if not value or len(value) > 500 or any(ord(char) < 33 for char in value) or '\\' in value:
        return ''
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower()
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port is not None:
            return ''
    except ValueError:
        return ''
    video_id = ''
    if host in ('youtu.be', 'www.youtu.be'):
        match = re.fullmatch(r'/([A-Za-z0-9_-]{11})/?', parsed.path)
        video_id = match.group(1) if match else ''
    elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
        if parsed.path == '/watch':
            values = parse_qs(parsed.query, keep_blank_values=True).get('v', [])
            video_id = values[0] if len(values) == 1 else ''
        else:
            match = re.fullmatch(r'/(?:embed|shorts|live)/([A-Za-z0-9_-]{11})/?', parsed.path)
            video_id = match.group(1) if match else ''
    elif host in ('youtube-nocookie.com', 'www.youtube-nocookie.com'):
        match = re.fullmatch(r'/embed/([A-Za-z0-9_-]{11})/?', parsed.path)
        video_id = match.group(1) if match else ''
    return f'https://www.youtube-nocookie.com/embed/{video_id}?rel=0' if _VIDEO_ID.fullmatch(video_id) else ''


def validate_youtube_url(value):
    if value and not youtube_embed_url(value):
        raise ValidationError('Dùng liên kết YouTube HTTPS hợp lệ (youtube.com hoặc youtu.be), không dán mã iframe.')


def validate_trailer_file(upload):
    """Validate newly uploaded H.264 MP4; never fetch a URL or re-probe saved media."""
    if not upload or getattr(upload, '_committed', False):
        return
    if upload.size > MAX_TRAILER_BYTES:
        raise ValidationError('Trailer tối đa 50 MB.')
    try:
        upload.seek(0)
        with tempfile.TemporaryDirectory(prefix='lumiere-trailer-') as directory:
            source = Path(directory) / 'trailer.mp4'
            count = 0
            with source.open('wb') as target:
                for chunk in upload.chunks():
                    count += len(chunk)
                    if count > MAX_TRAILER_BYTES:
                        raise ValidationError('Trailer tối đa 50 MB.')
                    target.write(chunk)
            with source.open('rb') as handle:
                header = handle.read(64)
            if len(header) < 16 or header[4:8] != b'ftyp' or header[8:12] not in (
                b'isom', b'iso2', b'iso3', b'iso4', b'iso5', b'iso6', b'mp41',
                b'mp42', b'avc1', b'M4V ', b'dash', b'MSNV',
            ):
                raise ValidationError('Chọn trailer MP4 mã hóa H.264; đổi đuôi file không chuyển đổi được video.')
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                 '-format_whitelist', 'mov', '-show_entries',
                 'format=format_name,duration:stream=codec_type,codec_name,width,height',
                 '-of', 'json', str(source)],
                capture_output=True, text=True, check=True, timeout=10,
            )
            data = json.loads(result.stdout)
            duration = float(data.get('format', {}).get('duration', 0))
            if not math.isfinite(duration) or not 0 < duration <= MAX_TRAILER_SECONDS:
                raise ValidationError('Trailer phải có thời lượng lớn hơn 0 và không quá 5 phút.')
            if 'mp4' not in data.get('format', {}).get('format_name', '').split(','):
                raise ValidationError('Trailer cần là file MP4 hợp lệ.')
            streams = data.get('streams', [])
            video = [stream for stream in streams if stream.get('codec_type') == 'video']
            audio = [stream for stream in streams if stream.get('codec_type') == 'audio']
            if len(video) != 1 or video[0].get('codec_name') != 'h264' or len(audio) > 1 or any(stream.get('codec_name') != 'aac' for stream in audio) or len(streams) != len(video) + len(audio):
                raise ValidationError('Dùng MP4 với một luồng H.264 và âm thanh AAC (nếu có).')
            if not 0 < video[0].get('width', 0) <= 4096 or not 0 < video[0].get('height', 0) <= 2160:
                raise ValidationError('Trailer hỗ trợ kích thước tối đa 4096 × 2160 px.')
    except ValidationError:
        raise
    except FileNotFoundError as error:
        raise ValidationError('Máy chủ cần cài ffprobe để kiểm tra trailer.') from error
    except (OSError, ValueError, TypeError, AttributeError, OverflowError, subprocess.SubprocessError) as error:
        raise ValidationError('Không đọc được trailer MP4 hoặc việc kiểm tra đã hết thời gian. Chọn file H.264 khác.') from error
    finally:
        with suppress(OSError, ValueError):
            upload.seek(0)
