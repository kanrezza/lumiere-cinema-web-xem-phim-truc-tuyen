"""Authenticated playback, signed HLS streaming and viewer progress."""

import math
import re
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.crypto import salted_hmac
from django.views.decorators.http import require_GET, require_POST

from ..access import require_watch
from ..models import Episode, History, Report


@login_required
def watch(request, pk):
    episode = get_object_or_404(Episode.objects.select_related('movie'), pk=pk)
    require_watch(request.user, episode)
    history = History.objects.filter(user=request.user, episode=episode).first()
    restarting = request.GET.get('start') == '1'
    position = history.position if history and not restarting and 0 < history.position < episode.duration - 1 else 0
    episodes = list(episode.movie.episodes.filter(status='ready'))
    next_episode = next((item for item in episodes if item.number > episode.number), None)
    return render(request, 'cinema/watch.html', {
        'episode': episode, 'position': position,
        'start_over_url': reverse('watch', args=[episode.pk]) + '?start=1' if position > 0 else '',
        'episodes': episodes, 'next_episode': next_episode,
        'duration_minutes': math.ceil(max(0, episode.duration) / 60),
    })


@login_required
@require_POST
def progress(request, pk):
    episode = get_object_or_404(Episode.objects.select_related('movie'), pk=pk)
    require_watch(request.user, episode)
    try: position = float(request.POST.get('position', 0))
    except ValueError: return JsonResponse({'error': 'Vị trí không hợp lệ'}, status=400)
    if not math.isfinite(position) or not 0 <= position <= episode.duration + 1: return JsonResponse({'error': 'Vị trí không hợp lệ'}, status=400)
    defaults = {'position': position}
    if position > 0:
        defaults['hidden_from_continue'] = False
    History.objects.update_or_create(user=request.user, episode=episode, defaults=defaults)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def report(request, pk):
    episode = get_object_or_404(Episode, pk=pk, movie__published=True)
    description = request.POST.get('description', '').strip()
    if 1 <= len(description) <= 1000:
        Report.objects.create(user=request.user, episode=episode, description=description)
        messages.success(request, 'Đã gửi báo lỗi cho quản trị viên.')
    return redirect('movie', slug=episode.movie.slug)


def _playback_claims(request, episode):
    return {
        'u': request.user.pk,
        's': salted_hmac('video-session', request.session.session_key).hexdigest(),
        'e': episode.pk,
    }


@login_required
@require_POST
def stream_ticket(request, pk):
    episode = get_object_or_404(Episode.objects.select_related('movie'), pk=pk)
    require_watch(request.user, episode)
    if not request.session.session_key: request.session.save()
    # One current browser session per account. DB session authentication is also required on every segment.
    cache.set(f'playback:{request.user.pk}', request.session.session_key, settings.STREAM_TOKEN_AGE + 60)
    token = signing.dumps(_playback_claims(request, episode), salt='video')
    return JsonResponse({'url': reverse('stream', args=[episode.pk, 'index.m3u8']) + '?' + urlencode({'token': token})})


@login_required
@require_GET
def stream(request, pk, filename):
    episode = get_object_or_404(Episode.objects.select_related('movie'), pk=pk)
    require_watch(request.user, episode)
    token = request.GET.get('token', '')
    try: ticket = signing.loads(token, salt='video', max_age=settings.STREAM_TOKEN_AGE)
    except signing.BadSignature: raise PermissionDenied('Nguồn phát đã hết hạn.')
    if ticket != _playback_claims(request, episode) or cache.get(f'playback:{request.user.pk}') != request.session.session_key:
        raise PermissionDenied('Phiên phát không hợp lệ.')
    if not re.fullmatch(r'(index\.m3u8|seg\d{5,}\.ts)', filename): raise Http404
    path = settings.PRIVATE_MEDIA_ROOT / 'hls' / str(episode.asset_id) / filename
    if not path.is_file(): raise Http404
    if filename == 'index.m3u8':
        lines = path.read_text().splitlines()
        content = '\n'.join(line if not line or line.startswith('#') else reverse('stream', args=[pk, line]) + '?' + urlencode({'token': token}) for line in lines)
        return HttpResponse(content, content_type='application/vnd.apple.mpegurl')
    return FileResponse(path.open('rb'), content_type='video/mp2t')
