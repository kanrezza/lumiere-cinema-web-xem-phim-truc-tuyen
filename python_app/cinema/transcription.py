"""Background speech recognition against a configured loopback-only service."""
import hashlib
import html
import json
import math
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from .models import Episode, Subtitle, SubtitleTranscription
from .subtitles import normalize_subtitle, subtitle_language_validator, _format_timestamp


class TranscriptionError(Exception):
    pass


def source_key(episode):
    value = f'{episode.asset_id}:{episode.source.name}:{settings.SPEECH_MODEL_VERSION}'
    return hashlib.sha256(value.encode()).hexdigest()


def local_speech_url():
    value = settings.SPEECH_API_URL
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ('http', 'https') or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
                or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/')
                or parsed.port is not None and not 0 < parsed.port < 65536):
            raise ValueError
    except ValueError as error:
        raise TranscriptionError('Dịch vụ nhận dạng lời thoại chưa sẵn sàng.') from error
    return value.rstrip('/') + '/transcribe'


def private_source_path(episode):
    if not episode.source or not 0 < episode.duration <= 10800:
        raise TranscriptionError('Cần file phim gốc và thời lượng không quá 3 giờ để tạo phụ đề tự động.')
    try:
        path = Path(episode.source.path).resolve(strict=True)
        if not path.is_relative_to(Path(settings.PRIVATE_MEDIA_ROOT).resolve()) or not path.is_file():
            raise ValueError
    except (OSError, ValueError, NotImplementedError) as error:
        raise TranscriptionError('Không tìm thấy file phim gốc trong kho riêng tư.') from error
    return path


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def recognize(episode, language):
    url = local_speech_url()
    payload = json.dumps({'source_path': str(private_source_path(episode)), 'language': language}).encode()
    headers = {'Content-Type': 'application/json'}
    if settings.SPEECH_API_TOKEN:
        headers['Authorization'] = 'Bearer ' + settings.SPEECH_API_TOKEN
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(Request(url, data=payload, headers=headers, method='POST'), timeout=settings.SPEECH_TIMEOUT) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError
        segments = data.get('segments')
        if not isinstance(segments, list) or len(segments) > 10000:
            raise ValueError
        if not segments:
            raise TranscriptionError('Không nhận dạng được lời thoại. Video có thể không có tiếng nói hoặc chỉ có nhạc.')
        language = data.get('language', '')
        subtitle_language_validator(language)
        cues = []
        for segment in segments:
            start, end = float(segment['start']), float(segment['end'])
            text = segment['text']
            if (not all(math.isfinite(value) for value in (start, end)) or not 0 <= start < end <= episode.duration + 1
                    or not isinstance(text, str) or not text.strip()):
                raise ValueError
            cues.append(f'{_format_timestamp(round(start * 1000))} --> {_format_timestamp(round(end * 1000))}\n{html.escape(text.strip(), quote=False)}')
        vtt = normalize_subtitle(ContentFile(('WEBVTT\n\n' + '\n\n'.join(cues) + '\n').encode(), name='speech.vtt'))
        return language.lower(), vtt
    except TranscriptionError:
        raise
    except (OSError, URLError, ValueError, TypeError, KeyError, ValidationError) as error:
        raise TranscriptionError('Chưa thể nhận dạng lời thoại. Kiểm tra dịch vụ xử lý rồi thử lại.') from error


def process_transcription(job_id):
    claimed_at = timezone.now()
    if not SubtitleTranscription.objects.filter(pk=job_id, status='pending').update(status='processing', error='', updated_at=claimed_at):
        return False
    job = SubtitleTranscription.objects.select_related('episode__movie').get(pk=job_id)
    try:
        if not job.episode.movie.published or job.episode.status != 'ready' or source_key(job.episode) != job.source_key:
            raise TranscriptionError('Nguồn phim đã thay đổi hoặc không còn sẵn sàng.')
        language, content = recognize(job.episode, job.language)
        with transaction.atomic():
            active = SubtitleTranscription.objects.select_for_update().get(pk=job.pk)
            current = Episode.objects.select_related('movie').get(pk=job.episode_id)
            if active.status != 'processing' or active.updated_at != claimed_at:
                return False
            if not current.movie.published or current.status != 'ready' or source_key(current) != job.source_key:
                raise TranscriptionError('Nguồn phim đã thay đổi hoặc không còn sẵn sàng.')
            # A curated track or another recognition job wins over generated text.
            track, _ = Subtitle.objects.get_or_create(episode=job.episode, language=language,
                defaults={'label': {'en': 'English · tự động', 'vi': 'Tiếng Việt · tự động'}.get(language, language + ' · tự động'), 'content': content})
            SubtitleTranscription.objects.filter(pk=job.pk).update(status='ready', subtitle=track,
                detected_language=language, error='', updated_at=timezone.now())
    except TranscriptionError as error:
        SubtitleTranscription.objects.filter(pk=job.pk, status='processing', updated_at=claimed_at).update(status='failed', error=str(error)[:300], updated_at=timezone.now())
    except KeyboardInterrupt:
        SubtitleTranscription.objects.filter(pk=job.pk, status='processing', updated_at=claimed_at).update(status='failed', error='Quá trình nhận dạng bị gián đoạn. Bạn có thể thử lại.', updated_at=timezone.now())
        raise
    except Exception:
        SubtitleTranscription.objects.filter(pk=job.pk, status='processing', updated_at=claimed_at).update(status='failed', error='Quá trình nhận dạng gặp lỗi. Bạn có thể thử lại.', updated_at=timezone.now())
    return True
