"""Private HLS renditions and request-time quality limits.

Rendition names stay flat so the existing authenticated stream route remains the
only way to fetch media. The encoder's metadata is private alongside its files.
"""

import json
import math
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from django.core.cache import cache
from django.core.exceptions import PermissionDenied


FREE_MAX_QUALITY = 720
VIP_MAX_QUALITY = 1440
QUALITY_LADDER = (360, 480, 720, 1080, 1440)
RENDITION_PLAYLIST = re.compile(r'q([1-9]\d{0,3})\.m3u8')
RENDITION_SEGMENT = re.compile(r'q([1-9]\d{0,3})_seg\d{5,}\.ts')
LEGACY_SEGMENT = re.compile(r'seg\d{5,}\.ts')


@dataclass(frozen=True)
class Rendition:
    height: int
    width: int
    video_height: int
    playlist: str
    bandwidth: int

    @property
    def label(self):
        return f'{self.height}p'

    def owns_segment(self, name):
        pattern = LEGACY_SEGMENT if self.playlist == 'index.m3u8' else RENDITION_SEGMENT
        match = pattern.fullmatch(name)
        return bool(match and (self.playlist == 'index.m3u8' or int(match[1]) == self.height))


def max_quality(user):
    return VIP_MAX_QUALITY if user.is_vip or user.is_staff else FREE_MAX_QUALITY


def probe_dimensions(source):
    input_format = ['-f', 'mpegts'] if Path(source).suffix == '.ts' else []
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
         *input_format,
         '-select_streams', 'v:0', '-show_entries',
         'stream=width,height,sample_aspect_ratio:stream_tags=rotate:stream_side_data=rotation',
         '-of', 'json', str(source)],
        capture_output=True, text=True, check=True, timeout=30,
    )
    streams = json.loads(result.stdout).get('streams', [])
    if not streams:
        raise ValueError('File không có kích thước video hợp lệ.')
    stream = streams[0]
    width, height = int(stream['width']), int(stream['height'])
    aspect = stream.get('sample_aspect_ratio', '1:1')
    if aspect not in ('N/A', '0:1'):
        numerator, denominator = (int(part) for part in aspect.split(':', 1))
        if numerator <= 0 or denominator <= 0 or numerator / denominator > 100:
            raise ValueError('Tỉ lệ điểm ảnh không hợp lệ.')
        width = round(width * numerator / denominator)
    rotation = stream.get('tags', {}).get('rotate', 0)
    for item in stream.get('side_data_list', []):
        if 'rotation' in item:
            rotation = item['rotation']
            break
    if round(float(rotation)) % 180:
        width, height = height, width
    if not 2 <= width <= 16384 or not 2 <= height <= 16384:
        raise ValueError('Kích thước video không được hỗ trợ.')
    return width, height


def encoding_renditions(width, height):
    """Use actual source detail, including portrait sources, without upscaling."""
    heights = [tier for tier in QUALITY_LADDER if tier <= min(width, height)]
    if not heights:
        heights = [max(2, min(width, height) // 2 * 2)]
    renditions = []
    for tier in heights:
        long_edge = math.floor(tier * 16 / 9 / 2) * 2
        bound_width, bound_height = (long_edge, tier) if width >= height else (tier, long_edge)
        scale = min(1, bound_width / width, bound_height / height)
        encoded_width = max(2, math.floor(width * scale / 2) * 2)
        encoded_height = max(2, math.floor(height * scale / 2) * 2)
        bitrate = next((rate for threshold, rate in ((360, 700000), (480, 1200000),
                        (720, 2500000), (1080, 4500000), (1440, 8000000)) if tier <= threshold), 8000000)
        renditions.append(Rendition(tier, encoded_width, encoded_height, f'q{tier}.m3u8', bitrate + 192000))
    return renditions


def write_quality_metadata(output, renditions):
    (output / 'quality.json').write_text(json.dumps({
        'version': 1, 'renditions': [asdict(item) for item in renditions],
    }), encoding='utf-8')


def master_playlist(renditions, url_for):
    lines = ['#EXTM3U', '#EXT-X-VERSION:3']
    for rendition in renditions:
        lines.extend([
            f'#EXT-X-STREAM-INF:BANDWIDTH={rendition.bandwidth},RESOLUTION={rendition.width}x{rendition.video_height}',
            url_for(rendition.playlist),
        ])
    return '\n'.join(lines) + '\n'


def media_segments(path, rendition):
    """Parse encoder-generated VOD media playlists; reject external/file URLs."""
    text = path.read_text(encoding='utf-8')
    if len(text) > 2 * 1024 * 1024 or not text.startswith('#EXTM3U'):
        raise ValueError('Danh sách phát không hợp lệ.')
    segments, headers, elapsed, duration = [], [], 0.0, None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('#EXTINF:'):
            duration = float(line.split(':', 1)[1].split(',', 1)[0])
            if not math.isfinite(duration) or not 0 < duration <= 60:
                raise ValueError('Đoạn video không hợp lệ.')
        elif not line.startswith('#'):
            if duration is None or not rendition.owns_segment(line):
                raise ValueError('Nguồn đoạn video không hợp lệ.')
            segments.append((line, elapsed, duration))
            elapsed += duration
            duration = None
        elif line.startswith(('#EXT-X-TARGETDURATION:', '#EXT-X-VERSION:')):
            headers.append(line)
        elif line.startswith(('#EXT-X-KEY:', '#EXT-X-MAP:', '#EXT-X-BYTERANGE:', '#EXT-X-STREAM-INF:')):
            raise ValueError('Định dạng HLS không được hỗ trợ.')
    if duration is not None or not segments:
        raise ValueError('Danh sách phát thiếu đoạn video.')
    return headers, segments


def _legacy_rendition(directory):
    """Existing single-rendition assets must be measured, never assumed720p."""
    provisional = Rendition(1, 2, 2, 'index.m3u8', 4000000)
    _, segments = media_segments(directory / 'index.m3u8', provisional)
    first = directory / segments[0][0]
    stat = first.stat()
    cache_key = f'legacy-hls-size:{directory.name}:{stat.st_size}:{stat.st_mtime_ns}'
    size = cache.get(cache_key)
    if size is None:
        size = probe_dimensions(first)
        cache.set(cache_key, size, 3600)
    width, height = size
    # A legacy stream must fit BOTH edges of the viewer's landscape/portrait box.
    required_quality = math.ceil(max(min(width, height), max(width, height) * 9 / 16))
    return [Rendition(required_quality, width, height, 'index.m3u8', 4000000)]


def asset_renditions(directory):
    metadata = directory / 'quality.json'
    if not metadata.is_file():
        try:
            return _legacy_rendition(directory)
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            raise PermissionDenied('Nguồn cũ chưa xác minh được chất lượng. Vui lòng báo quản trị viên xử lý lại video.')
    try:
        if metadata.stat().st_size > 32768:
            raise ValueError
        document = json.loads(metadata.read_text(encoding='utf-8'))
        if not isinstance(document, dict) or document.get('version') != 1 or not 1 <= len(document['renditions']) <= len(QUALITY_LADDER):
            raise ValueError
        renditions = []
        for item in document['renditions']:
            rendition = Rendition(**item)
            if not all(type(value) is int for value in (rendition.height, rendition.width, rendition.video_height, rendition.bandwidth)):
                raise ValueError
            if not 2 <= rendition.height <= VIP_MAX_QUALITY or not 2 <= rendition.width <= 2560 or not 2 <= rendition.video_height <= 2560:
                raise ValueError
            if not 1000 <= rendition.bandwidth <= 100000000:
                raise ValueError
            if rendition.playlist != f'q{rendition.height}.m3u8' or not (directory / rendition.playlist).is_file():
                raise ValueError
            if max(min(rendition.width, rendition.video_height), max(rendition.width, rendition.video_height) * 9 / 16) > rendition.height + 1:
                raise ValueError
            renditions.append(rendition)
        if len({item.height for item in renditions}) != len(renditions):
            raise ValueError
        return sorted(renditions, key=lambda item: item.height)
    except (OSError, ValueError, KeyError, TypeError):
        raise PermissionDenied('Thông tin chất lượng video không hợp lệ. Vui lòng báo quản trị viên.')


def permitted_renditions(user, directory, *, renditions=None):
    source = asset_renditions(directory) if renditions is None else renditions
    available = [item for item in source if item.height <= max_quality(user)]
    if not available:
        raise PermissionDenied('Chưa có bản phát phù hợp với gói của bạn. Vui lòng báo quản trị viên xử lý lại video.')
    return available
