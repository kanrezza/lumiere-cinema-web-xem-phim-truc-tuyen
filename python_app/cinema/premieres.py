"""Server-clock premiere policy shared by pages and signed video delivery."""

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from urllib.parse import urlencode
from uuid import UUID

from .access import can_watch, require_watch
from .models import Premiere
from .rooms.identity import room_user_profile


def can_manage_premieres(user):
    return bool(user.is_authenticated and user.is_active and user.is_staff and user.has_perm('cinema.manage_premieres'))


def premiere_requires_vip(premiere):
    return premiere.audience == Premiere.Audience.VIP or premiere.episode.movie.is_vip


def can_view_premiere(user, premiere):
    return can_watch(user, premiere.episode) and (
        not premiere_requires_vip(premiere) or user.is_vip or user.is_staff
    )


def premiere_phase(premiere, now=None):
    now = timezone.now() if now is None else now
    if premiere.status in (Premiere.Status.ENDED, Premiere.Status.CANCELLED):
        return premiere.status
    start = premiere.started_at or premiere.scheduled_at
    if now < start:
        return Premiere.Status.SCHEDULED
    return Premiere.Status.ENDED if (now - start).total_seconds() >= premiere.episode.duration else Premiere.Status.LIVE


def premiere_stream_limit(premiere, now=None):
    now = timezone.now() if now is None else now
    start = premiere.started_at or premiere.scheduled_at
    stop = min(now, premiere.ended_at) if premiere.ended_at else now
    return max(0., min(float(premiere.episode.duration), (stop - start).total_seconds()))


def require_premiere_playback(request, episode, *, allow_ended=False):
    """Normal VOD stays independent; premiere URLs always re-check live access."""
    value = request.GET.get('premiere')
    if value is None:
        return None
    try:
        premiere_id = UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise PermissionDenied('Suất công chiếu không hợp lệ.')
    premiere = get_object_or_404(Premiere.objects.select_related('episode__movie'), pk=premiere_id, episode=episode)
    require_watch(request.user, episode)
    phases = (Premiere.Status.LIVE, Premiere.Status.ENDED) if allow_ended else (Premiere.Status.LIVE,)
    if not can_view_premiere(request.user, premiere) or premiere_phase(premiere) not in phases:
        raise PermissionDenied('Suất công chiếu chưa bắt đầu, đã kết thúc hoặc bạn chưa có quyền xem.')
    return premiere


def premiere_messages(premiere):
    entries = list(premiere.messages.filter(hidden=False).select_related('user').order_by('-pk')[:60])
    return [{
        'id': entry.pk, 'user_id': entry.user_id, 'user': entry.user.username, 'username': entry.user.username,
        'content': entry.content, 'created_at': entry.created_at.isoformat(),
        **room_user_profile(entry.user),
    } for entry in reversed(entries)]


def premiere_state(premiere, user, now=None, *, include_messages=True):
    now = timezone.now() if now is None else now
    phase = premiere_phase(premiere, now)
    allowed = can_view_premiere(user, premiere)
    position = premiere_stream_limit(premiere, now)
    return {
        'id': str(premiere.pk), 'title': premiere.title,
        'movie_title': premiere.episode.movie.title, 'episode_title': premiere.episode.title,
        'episode_id': premiere.episode_id, 'status': phase,
        'scheduled_at': premiere.scheduled_at.isoformat(),
        'started_at': (premiere.started_at or premiere.scheduled_at).isoformat(),
        'server_time': now.isoformat(), 'position': position,
        'playback_delay_seconds': 12, 'playback_position': max(0., position - 12),
        'ended_at': premiere.ended_at.isoformat() if premiere.ended_at else None,
        'ended_manually': bool(premiere.ended_at),
        'duration': premiere.episode.duration,
        'playing': allowed and phase == Premiere.Status.LIVE,
        'can_watch': allowed, 'requires_vip': premiere_requires_vip(premiere),
        'can_chat': allowed and phase in (Premiere.Status.SCHEDULED, Premiere.Status.LIVE),
        'can_manage': can_manage_premieres(user), 'state_version': premiere.state_version,
        'ticket_url': reverse('ticket', args=[premiere.episode_id]) + '?' + urlencode({'premiere': premiere.pk}) if allowed and phase == Premiere.Status.LIVE else '',
        'messages': premiere_messages(premiere) if allowed and include_messages else [],
    }
