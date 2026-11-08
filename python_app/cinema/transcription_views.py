from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Episode, SubtitleTranscription
from .transcription import TranscriptionError, local_speech_url, private_source_path, source_key
from .views import require_watch


def allow_request(user):
    key = f'transcription:{user.pk}'
    if cache.add(key, 1, 3600):
        return True
    try:
        return cache.incr(key) <= 3
    except ValueError:
        return False


def payload(job):
    track = job.subtitle if job.status == 'ready' else None
    return {'id': str(job.pk), 'status': job.status, 'error': job.error,
            'status_url': reverse('caption_generation_status', args=[job.episode_id, job.pk]),
            'subtitle': {'id': track.pk, 'language': track.language, 'label': track.label,
                         'url': reverse('subtitle', args=[job.episode_id, track.pk]),
                         'translate_url': reverse('subtitle_translate', args=[job.episode_id, track.pk])} if track else None}


@login_required
@require_POST
def generate(request, pk):
    episode = get_object_or_404(Episode.objects.select_related('movie'), pk=pk)
    require_watch(request.user, episode)
    language = request.POST.get('language', 'auto')
    if language not in ('auto', 'en', 'vi'):
        return JsonResponse({'error': 'Chọn ngôn ngữ lời thoại hợp lệ.'}, status=400)
    try:
        local_speech_url()
        private_source_path(episode)
    except TranscriptionError as error:
        return JsonResponse({'error': str(error)}, status=503)
    version = source_key(episode)
    existing = SubtitleTranscription.objects.filter(episode=episode, source_key=version, language=language).select_related('subtitle').first()
    if existing:
        if existing.status == 'ready' and not existing.subtitle_id:
            existing.status = 'failed'
            existing.error = 'Phụ đề đã bị xóa. Bạn có thể yêu cầu tạo lại.'
            existing.save(update_fields=['status', 'error', 'updated_at'])
        if existing.status == 'failed' and request.POST.get('retry') == '1':
            if SubtitleTranscription.objects.filter(status__in=('pending', 'processing')).count() >= 10:
                return JsonResponse({'error': 'Đang có nhiều video cần xử lý. Hãy thử lại sau.'}, status=429)
            if not cache.add(f'transcription-retry:{existing.pk}', True, 30) or not allow_request(request.user):
                return JsonResponse({'error': 'Hãy đợi một lúc trước khi tạo lại phụ đề.'}, status=429)
            SubtitleTranscription.objects.filter(pk=existing.pk, status='failed').update(status='pending', error='', requested_by=request.user, updated_at=timezone.now())
            existing.refresh_from_db()
        return JsonResponse(payload(existing), status=200 if existing.status in ('ready', 'failed') else 202)
    if not allow_request(request.user):
        return JsonResponse({'error': 'Bạn đã yêu cầu tạo nhiều phụ đề. Hãy thử lại sau.'}, status=429)
    if SubtitleTranscription.objects.filter(status__in=('pending', 'processing')).count() >= 10:
        return JsonResponse({'error': 'Đang có nhiều video cần xử lý. Hãy thử lại sau.'}, status=429)
    job, _ = SubtitleTranscription.objects.get_or_create(episode=episode, source_key=version, language=language,
        defaults={'requested_by': request.user})
    return JsonResponse(payload(job), status=202)


@login_required
@require_GET
def status(request, pk, job_pk):
    job = get_object_or_404(SubtitleTranscription.objects.select_related('episode__movie', 'subtitle'), pk=job_pk, episode_id=pk)
    require_watch(request.user, job.episode)
    if source_key(job.episode) != job.source_key or job.status == 'ready' and not job.subtitle_id:
        return JsonResponse({'error': 'Nguồn phụ đề đã thay đổi. Hãy yêu cầu tạo lại.'}, status=409)
    response = JsonResponse(payload(job))
    response['Cache-Control'] = 'private, no-store'
    return response
