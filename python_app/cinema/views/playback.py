"""Authenticated playback, signed HLS streaming and viewer progress."""

import math
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
from ..rooms.access import host_capacity
from ..video_quality import (LEGACY_SEGMENT, RENDITION_PLAYLIST, RENDITION_SEGMENT,
                             asset_renditions, master_playlist, max_quality, media_segments, permitted_renditions)
from ..premieres import require_premiere_playback, premiere_phase, premiere_stream_limit


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
        'episode': episode, 'position': position, 'room_capacity': host_capacity(request.user),
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


def _playback_claims(request, episode, premiere=None):
    claims = {
        'u': request.user.pk,
        's': salted_hmac('video-session', request.session.session_key).hexdigest(),
        'e': episode.pk,
    }
    if premiere is not None:
        claims['p'] = str(premiere.pk)
    return claims


def _stream_url(episode_id, filename, token, premiere=None):
    params = {'token': token}
    if premiere is not None:
        params['premiere'] = str(premiere.pk)
    return reverse('stream', args=[episode_id, filename]) + '?' + urlencode(params)


@login_required
@require_POST
def stream_ticket(request, pk):
    episode = get_object_or_404(Episode.objects.select_related('movie'), pk=pk)
    require_watch(request.user, episode)
    premiere = require_premiere_playback(request, episode)
    directory = settings.PRIVATE_MEDIA_ROOT / 'hls' / str(episode.asset_id)
    source_qualities = asset_renditions(directory)
    qualities = permitted_renditions(request.user, directory, renditions=source_qualities)
    if not request.session.session_key:
        request.session.save()
    # One current browser session per account. Every segment rechecks authentication,
    # the subscription and any premiere scope, including after a ticket was issued.
    cache.set(f'playback:{request.user.pk}', request.session.session_key, settings.STREAM_TOKEN_AGE + 60)
    token = signing.dumps(_playback_claims(request, episode, premiere), salt='video')
    return JsonResponse({
        'url': _stream_url(episode.pk, 'index.m3u8', token, premiere),
        'qualities': [{'height': item.height, 'label': item.label,
                       'url': _stream_url(episode.pk, item.playlist, token, premiere)} for item in qualities],
        'max_quality': max_quality(request.user),
        'source_max_quality': max(item.height for item in source_qualities),
    })


def _media_manifest(path, rendition, url_for, premiere=None):
    try:
        headers, segments = media_segments(path, rendition)
    except (OSError, ValueError, KeyError, TypeError):
        raise Http404
    lines = ['#EXTM3U', *headers]
    if not any(line.startswith('#EXT-X-TARGETDURATION:') for line in headers):
        lines.append(f'#EXT-X-TARGETDURATION:{math.ceil(max(segment[2] for segment in segments))}')
    lines.extend(['#EXT-X-MEDIA-SEQUENCE:0', '#EXT-X-INDEPENDENT-SEGMENTS'])
    limit = premiere_stream_limit(premiere) if premiere is not None else math.inf
    live = premiere is not None and premiere_phase(premiere) == 'live'
    lines.append('#EXT-X-PLAYLIST-TYPE:EVENT' if live else '#EXT-X-PLAYLIST-TYPE:VOD')
    for name, start, duration in segments:
        # The final encoded segment may include a few milliseconds of AAC/video
        # padding beyond ffprobe's source duration. Natural completion unlocks it.
        if start + duration <= limit + .001 or (premiere is not None and limit >= premiere.episode.duration):
            lines.extend([f'#EXTINF:{duration:.6f},', url_for(name)])
    if not live:
        lines.append('#EXT-X-ENDLIST')
    return '\n'.join(lines) + '\n'


@login_required
@require_GET
def stream(request, pk, filename):
    episode = get_object_or_404(Episode.objects.select_related('movie'), pk=pk)
    require_watch(request.user, episode)
    premiere = require_premiere_playback(request, episode, allow_ended=True)
    token = request.GET.get('token', '')
    try:
        ticket = signing.loads(token, salt='video', max_age=settings.STREAM_TOKEN_AGE)
    except signing.BadSignature:
        raise PermissionDenied('Nguồn phát đã hết hạn.')
    if ticket != _playback_claims(request, episode, premiere) or cache.get(f'playback:{request.user.pk}') != request.session.session_key:
        raise PermissionDenied('Phiên phát không hợp lệ.')
    if filename != 'index.m3u8' and not any(pattern.fullmatch(filename) for pattern in (RENDITION_PLAYLIST, RENDITION_SEGMENT, LEGACY_SEGMENT)):
        raise Http404
    directory = settings.PRIVATE_MEDIA_ROOT / 'hls' / str(episode.asset_id)
    qualities = permitted_renditions(request.user, directory)
    url_for = lambda name: _stream_url(pk, name, token, premiere)
    if filename == 'index.m3u8' and qualities[0].playlist != 'index.m3u8':
        response = HttpResponse(master_playlist(qualities, url_for), content_type='application/vnd.apple.mpegurl')
    else:
        rendition = next((item for item in qualities if item.playlist == filename or item.owns_segment(filename)), None)
        if rendition is None:
            if (RENDITION_PLAYLIST.fullmatch(filename) or RENDITION_SEGMENT.fullmatch(filename)):
                raise PermissionDenied('Chất lượng video này cần gói VIP còn hiệu lực.')
            raise Http404
        path = directory / filename
        if not path.is_file():
            raise Http404
        if filename.endswith('.m3u8'):
            response = HttpResponse(_media_manifest(path, rendition, url_for, premiere), content_type='application/vnd.apple.mpegurl')
        else:
            try:
                _, segments = media_segments(directory / rendition.playlist, rendition)
            except (OSError, ValueError, KeyError, TypeError):
                raise Http404
            segment = next((item for item in segments if item[0] == filename), None)
            if segment is None:
                raise Http404
            if premiere is not None:
                limit = premiere_stream_limit(premiere)
                if segment[1] + segment[2] > limit + .001 and limit < episode.duration:
                    raise PermissionDenied('Đoạn phim này chưa được công chiếu.')
            response = FileResponse(path.open('rb'), content_type='video/mp2t')
    response['Cache-Control'] = 'private, no-store'
    return response
