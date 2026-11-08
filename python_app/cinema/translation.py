"""Translate subtitle text through an explicitly configured local/HTTPS service."""
import hashlib
import html
import ipaddress
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils import timezone

from .subtitles import MAX_CUE_CHARACTERS, MAX_SUBTITLE_BYTES, normalize_subtitle


LANGUAGE_LABELS = {'vi': 'Tiếng Việt', 'en': 'English', 'es': 'Español', 'fr': 'Français', 'de': 'Deutsch', 'it': 'Italiano', 'pt': 'Português', 'ru': 'Русский', 'ja': '日本語', 'ko': '한국어', 'zh': '中文', 'ar': 'العربية', 'hi': 'हिन्दी', 'id': 'Bahasa Indonesia', 'th': 'ภาษาไทย'}
MAX_BATCH_CUES = 16
MAX_BATCH_CHARACTERS = 16000
MAX_SEGMENT_CHARACTERS = 500
MAX_TRANSLATION_SECONDS = 900
MAX_PROVIDER_RESPONSE = 512 * 1024


class TranslationError(Exception):
    pass


def configured_targets():
    return tuple(code for code in settings.TRANSLATION_TARGETS if code in LANGUAGE_LABELS)


def service_url():
    """Only operator configuration determines the destination, never a request."""
    value = settings.TRANSLATION_API_URL.strip().rstrip('/')
    if not value:
        raise TranslationError('Dịch tự động chưa được cấu hình trên máy chủ.')
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ''
        local = host == 'localhost'
        try:
            local = local or ipaddress.ip_address(host).is_loopback
        except ValueError:
            pass
        valid = parsed.scheme == 'https' or parsed.scheme == 'http' and local
        if not valid or not host or parsed.username or parsed.password or parsed.query or parsed.fragment or '\\' in value or any(ord(char) < 33 for char in value):
            raise ValueError
        parsed.port
    except ValueError as error:
        raise TranslationError('Cấu hình máy chủ dịch không hợp lệ.') from error
    return value


def provider_key():
    return hashlib.sha256((service_url() + '\0' + settings.TRANSLATION_PROVIDER_VERSION).encode()).hexdigest()


def source_snapshot(subtitle):
    language = subtitle.language.strip().lower().split('-')[0]
    if language not in LANGUAGE_LABELS:
        raise TranslationError('Ngôn ngữ phụ đề gốc chưa được hỗ trợ dịch tự động.')
    try:
        content = normalize_subtitle(ContentFile(subtitle.content.encode('utf-8'), name='source.vtt'))
    except (ValidationError, UnicodeError, AttributeError) as error:
        raise TranslationError('Phụ đề gốc không hợp lệ để dịch.') from error
    digest = hashlib.sha256((language + '\0' + content).encode()).hexdigest()
    return language, content, digest


def current_source_hash(subtitle):
    return source_snapshot(subtitle)[2]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request_json(path, payload=None):
    headers = {'Accept': 'application/json'}
    body = None
    if payload is not None:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = Request(service_url() + path, data=body, headers=headers, method='POST' if body is not None else 'GET')
    try:
        with build_opener(_NoRedirect(), ProxyHandler({})).open(request, timeout=settings.TRANSLATION_TIMEOUT) as response:
            raw = response.read(MAX_PROVIDER_RESPONSE + 1)
        if len(raw) > MAX_PROVIDER_RESPONSE:
            raise TranslationError('Máy chủ dịch trả về dữ liệu quá lớn.')
        return json.loads(raw.decode('utf-8'))
    except TranslationError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, UnicodeError) as error:
        # Never expose URLs, credentials, source text or raw provider errors.
        raise TranslationError('Chưa kết nối được máy chủ dịch. Vui lòng thử lại sau.') from error


def _supported_pair(source, target):
    data = _request_json('/languages')
    if not isinstance(data, list):
        raise TranslationError('Máy chủ dịch trả về danh sách ngôn ngữ không hợp lệ.')
    for row in data:
        if isinstance(row, dict) and row.get('code') == source:
            targets = row.get('targets', [])
            if isinstance(targets, list) and target in targets:
                return
    raise TranslationError('Máy chủ dịch chưa có mô hình cho cặp ngôn ngữ này.')


def _translated_batch(texts, source, target):
    payload = {'q': texts, 'source': source, 'target': target, 'format': 'text'}
    if settings.TRANSLATION_API_KEY:
        payload['api_key'] = settings.TRANSLATION_API_KEY
    result = _request_json('/translate', payload)
    translated = result.get('translatedText') if isinstance(result, dict) else None
    if isinstance(translated, str) and len(texts) == 1:
        translated = [translated]
    if not isinstance(translated, list) or len(translated) != len(texts):
        raise TranslationError('Máy chủ dịch trả về số câu không hợp lệ.')
    cleaned = []
    for value in translated:
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_CUE_CHARACTERS:
            raise TranslationError('Máy chủ dịch trả về nội dung câu không hợp lệ.')
        if any(ord(char) < 32 and char not in '\n\t\r' for char in value):
            raise TranslationError('Bản dịch chứa ký tự điều khiển không hợp lệ.')
        value = value.replace('\r\n', '\n').replace('\r', '\n')
        value = re.sub(r'\n[ \t]*\n+', '\n', value.strip())
        cleaned.append(html.escape(value, quote=False))
    return cleaned


def translate_vtt(content, source, target):
    """Translate cue text in bounded batches and retain every original timing."""
    _supported_pair(source, target)
    canonical = normalize_subtitle(ContentFile(content.encode('utf-8'), name='source.vtt'))
    blocks = canonical.strip().split('\n\n')[1:]
    timings, texts = [], []
    for block in blocks:
        timing, text = block.split('\n', 1)
        timings.append(timing)
        texts.append(html.unescape(text))
    # Caption timing is independent from inference segmentation. Split long
    # cues rather than silently truncating them at a model's token limit.
    segments, cue_sizes = [], []
    for text in texts:
        parts = []
        remaining = text
        while len(remaining) > MAX_SEGMENT_CHARACTERS:
            boundary = remaining.rfind(' ', 0, MAX_SEGMENT_CHARACTERS + 1)
            if boundary < MAX_SEGMENT_CHARACTERS // 2:
                boundary = MAX_SEGMENT_CHARACTERS
            parts.append(remaining[:boundary])
            remaining = remaining[boundary:].lstrip(' ')
        if remaining:
            parts.append(remaining)
        segments.extend(parts)
        cue_sizes.append(len(parts))
    translated = []
    batch = []
    count = 0
    deadline = time.monotonic() + MAX_TRANSLATION_SECONDS
    for text in segments:
        if time.monotonic() > deadline:
            raise TranslationError('Bản dịch đã vượt quá thời gian xử lý. Hãy thử phụ đề ngắn hơn.')
        if batch and (len(batch) >= MAX_BATCH_CUES or count + len(text) > MAX_BATCH_CHARACTERS):
            translated.extend(_translated_batch(batch, source, target))
            batch, count = [], 0
        batch.append(text)
        count += len(text)
    if batch:
        translated.extend(_translated_batch(batch, source, target))
    translated_cues = []
    offset = 0
    for size in cue_sizes:
        translated_cues.append(' '.join(translated[offset:offset + size]))
        offset += size
    output = 'WEBVTT\n\n' + '\n\n'.join(f'{timing}\n{text}' for timing, text in zip(timings, translated_cues, strict=True)) + '\n'
    if len(output.encode('utf-8')) > MAX_SUBTITLE_BYTES:
        raise TranslationError('Bản dịch vượt quá dung lượng phụ đề cho phép.')
    return normalize_subtitle(ContentFile(output.encode('utf-8'), name='translated.vtt'))


def process_translation(job):
    """Run one claimed job; partial results are never published."""
    from .models import SubtitleTranslation
    try:
        if provider_key() != job.provider_key:
            raise TranslationError('Cấu hình dịch đã thay đổi. Hãy yêu cầu bản dịch mới.')
        if current_source_hash(job.subtitle) != job.source_hash:
            raise TranslationError('Phụ đề gốc đã đổi. Hãy yêu cầu bản dịch mới.')
        result = translate_vtt(job.source_content, job.source_language, job.target_language)
    except (TranslationError, ValidationError) as error:
        message = str(error)
        SubtitleTranslation.objects.filter(pk=job.pk, status='processing').update(status='failed', error=message[:300], content='', updated_at=timezone.now(), finished_at=timezone.now())
        return False
    SubtitleTranslation.objects.filter(pk=job.pk, status='processing').update(status='ready', error='', content=result, updated_at=timezone.now(), finished_at=timezone.now())
    return True
