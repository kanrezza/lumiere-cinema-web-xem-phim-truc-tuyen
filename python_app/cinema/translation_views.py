"""Authenticated translation jobs; expensive inference runs only in a worker."""
from django.contrib.auth.decorators import login_required
from datetime import timedelta
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Subtitle, SubtitleTranslation, User
from .translation import LANGUAGE_LABELS, TranslationError, configured_targets, current_source_hash, provider_key, source_snapshot
from .views import require_watch


def _json(data, status=200):
    response = JsonResponse(data, status=status)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def _job_data(job):
    return {'id': str(job.pk), 'status': job.status, 'target': job.target_language,
            'label': LANGUAGE_LABELS.get(job.target_language, job.target_language) + ' (dịch tự động)',
            'status_url': reverse('subtitle_translation_status', args=[job.subtitle.episode_id, job.pk]),
            'track_url': reverse('subtitle_translation_track', args=[job.subtitle.episode_id, job.pk]) if job.status == 'ready' else None,
            'error': job.error if job.status == 'failed' else ''}


def _allow_new_job(user):
    key = f'subtitle-translation:{user.pk}'
    if cache.add(key, 1, 3600):
        return True
    try:
        return cache.incr(key) <= 12
    except ValueError:
        return False


@login_required
@require_POST
def subtitle_translate(request, pk, subtitle_pk):
    track = get_object_or_404(Subtitle.objects.select_related('episode__movie'), pk=subtitle_pk, episode_id=pk)
    require_watch(request.user, track.episode)
    target = request.POST.get('target', '').strip().lower()
    if target not in configured_targets():
        return _json({'error': 'Ngôn ngữ đích chưa được hỗ trợ.'}, status=400)
    try:
        provider = provider_key()
        language, content, digest = source_snapshot(track)
    except TranslationError as error:
        return _json({'error': str(error)}, status=503)
    if target == language:
        return _json({'error': 'Chọn ngôn ngữ khác với phụ đề gốc.'}, status=400)
    lookup = {'subtitle': track, 'source_hash': digest, 'target_language': target, 'provider_key': provider}
    existing = SubtitleTranslation.objects.filter(**lookup).first()
    retrying = existing and existing.status == 'failed' and request.POST.get('retry') == '1'
    if existing and not retrying:
        return _json(_job_data(existing), status=200 if existing.status in ('ready', 'failed') else 202)
    if retrying and existing.updated_at > timezone.now() - timedelta(seconds=30):
        return _json({'error': 'Hãy đợi 30 giây trước khi thử dịch lại.'}, status=429)
    if not _allow_new_job(request.user):
        return _json({'error': 'Bạn đã yêu cầu quá nhiều bản dịch. Vui lòng thử lại sau.'}, status=429)
    with transaction.atomic():
        User.objects.select_for_update().get(pk=request.user.pk)
        if SubtitleTranslation.objects.filter(requested_by=request.user, status__in=['pending', 'processing']).count() >= 3:
            return _json({'error': 'Bạn đang có 3 bản dịch chờ xử lý. Hãy đợi hoàn tất.'}, status=429)
        job, _ = SubtitleTranslation.objects.select_for_update().get_or_create(**lookup, defaults={'source_language': language, 'source_content': content, 'requested_by': request.user})
        if retrying and job.status == 'failed':
            job.status, job.error, job.content = 'pending', '', ''
            # The viewer who queues this attempt owns its pending-job quota.
            job.requested_by = request.user
            job.started_at = job.finished_at = None
            job.save(update_fields=['status', 'error', 'content', 'requested_by', 'started_at', 'finished_at', 'updated_at'])
    return _json(_job_data(job), status=200 if job.status in ('ready', 'failed') else 202)


def _authorized_job(request, pk, translation_pk):
    job = get_object_or_404(SubtitleTranslation.objects.select_related('subtitle__episode__movie'), pk=translation_pk, subtitle__episode_id=pk)
    require_watch(request.user, job.subtitle.episode)
    return job


def _stale(job):
    try:
        return current_source_hash(job.subtitle) != job.source_hash
    except TranslationError:
        return True


@login_required
@require_GET
def subtitle_translation_status(request, pk, translation_pk):
    job = _authorized_job(request, pk, translation_pk)
    if _stale(job):
        return _json({'error': 'Phụ đề gốc đã đổi. Hãy yêu cầu bản dịch mới.'}, status=409)
    return _json(_job_data(job))


@login_required
@require_GET
def subtitle_translation_track(request, pk, translation_pk):
    job = _authorized_job(request, pk, translation_pk)
    if _stale(job):
        return _json({'error': 'Phụ đề gốc đã đổi. Hãy yêu cầu bản dịch mới.'}, status=409)
    if job.status != 'ready' or not job.content:
        return _json({'error': 'Bản dịch chưa sẵn sàng.'}, status=409)
    response = HttpResponse(job.content, content_type='text/vtt; charset=utf-8')
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
