"""Bounded SRT/WebVTT uploads are normalized to inert, plain-text WebVTT."""
import html
from contextlib import suppress
from pathlib import Path
import re

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator


MAX_SUBTITLE_BYTES = 2 * 1024 * 1024
MAX_SUBTITLE_CUES = 10000
MAX_CUE_CHARACTERS = 16000
MAX_SUBTITLE_SECONDS = 7 * 24 * 60 * 60
subtitle_language_validator = RegexValidator(
    r'\A[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8}){0,3}\Z',
    'Dùng mã ngôn ngữ như vi, en, en-US hoặc zh-Hant.',
)
_TIMESTAMP = r'(?:\d{2,6}:)?[0-5]\d:[0-5]\d[.,]\d{3}'
_TIMING = re.compile(rf'\A({_TIMESTAMP})[ \t]+-->[ \t]+({_TIMESTAMP})(?:[ \t]+[^\n]*)?\Z')


def _milliseconds(value):
    parts = value.replace(',', '.').split(':')
    hours, minutes, seconds = (['0'] + parts) if len(parts) == 2 else parts
    whole, fraction = seconds.split('.')
    result = (int(hours) * 3600 + int(minutes) * 60 + int(whole)) * 1000 + int(fraction)
    if result > MAX_SUBTITLE_SECONDS * 1000:
        raise ValidationError('Mốc thời gian phụ đề không được vượt quá 7 ngày.')
    return result


def _format_timestamp(milliseconds):
    seconds, fraction = divmod(milliseconds, 1000)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02}:{minutes:02}:{seconds:02}.{fraction:03}'


def normalize_subtitle(upload):
    """Read at most 2 MiB and return canonical VTT, never a path or raw upload."""
    suffix = Path(upload.name).suffix.lower()
    if suffix not in ('.srt', '.vtt'):
        raise ValidationError('Chọn file phụ đề .srt hoặc .vtt mã hóa UTF-8.')
    if getattr(upload, 'size', 0) > MAX_SUBTITLE_BYTES:
        raise ValidationError('Phụ đề tối đa 2 MB.')
    try:
        upload.seek(0)
        raw = upload.read(MAX_SUBTITLE_BYTES + 1)
        if len(raw) > MAX_SUBTITLE_BYTES:
            raise ValidationError('Phụ đề tối đa 2 MB.')
        text = raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    except (UnicodeDecodeError, AttributeError, OSError, ValueError) as error:
        raise ValidationError('Không đọc được phụ đề. Hãy lưu file bằng UTF-8.') from error
    finally:
        with suppress(OSError, ValueError):
            upload.seek(0)
    if not text.strip() or any(ord(char) < 32 and char not in '\n\t' for char in text):
        raise ValidationError('Phụ đề rỗng hoặc chứa ký tự điều khiển không hợp lệ.')
    if suffix == '.vtt':
        header, separator, text = text.partition('\n')
        if not separator or not re.fullmatch(r'WEBVTT(?:[ \t][^<>]*)?', header):
            raise ValidationError('File VTT cần bắt đầu bằng WEBVTT và một dòng trống.')
        if text and not text.startswith('\n'):
            raise ValidationError('Không hỗ trợ metadata hoặc tham chiếu ngoài trong header VTT.')
    elif text.startswith('WEBVTT'):
        raise ValidationError('Lưu nội dung WebVTT bằng đuôi .vtt.')
    if not text.strip():
        raise ValidationError('Phụ đề cần có ít nhất một câu hợp lệ.')

    cues = []
    previous_start = -1
    for block in re.split(r'\n[ \t]*\n', text.strip()):
        lines = block.splitlines()
        if suffix == '.vtt' and re.match(r'\ANOTE(?:[ \t]|\Z)', lines[0]):
            continue
        if lines[0].strip() in ('STYLE', 'REGION'):
            raise ValidationError('Không hỗ trợ STYLE hoặc REGION; dùng phụ đề văn bản thuần.')
        index = 0 if '-->' in lines[0] else 1
        if index >= len(lines):
            raise ValidationError('Mỗi câu phụ đề cần mốc bắt đầu, kết thúc và nội dung.')
        timing = _TIMING.fullmatch(lines[index].strip())
        if not timing or not lines[index + 1:]:
            raise ValidationError('Mốc thời gian phụ đề không hợp lệ hoặc thiếu nội dung.')
        start, end = map(_milliseconds, timing.groups())
        if end <= start or start < previous_start:
            raise ValidationError('Thời gian kết thúc phải sau bắt đầu; sắp câu phụ đề theo mốc bắt đầu.')
        previous_start = start
        content = '\n'.join(lines[index + 1:]).strip()
        if not content or len(content) > MAX_CUE_CHARACTERS:
            raise ValidationError('Nội dung mỗi câu phụ đề cần từ 1 đến 16.000 ký tự.')
        # VTT cue markup is not HTML. Escape it anyway so uploads cannot set
        # classes, voices, timestamps or links; it displays as literal text.
        content = html.escape(html.unescape(content), quote=False)
        cues.append(f'{_format_timestamp(start)} --> {_format_timestamp(end)}\n{content}')
        if len(cues) > MAX_SUBTITLE_CUES:
            raise ValidationError('Phụ đề tối đa 10.000 câu.')
    if not cues:
        raise ValidationError('Phụ đề cần có ít nhất một câu hợp lệ.')
    normalized = 'WEBVTT\n\n' + '\n\n'.join(cues) + '\n'
    if len(normalized.encode('utf-8')) > MAX_SUBTITLE_BYTES:
        raise ValidationError('Phụ đề sau chuẩn hóa vượt quá 2 MB.')
    return normalized
