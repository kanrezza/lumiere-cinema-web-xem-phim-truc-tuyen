"""Room media snapshots and player context shared by room endpoints."""

from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from ..access import can_watch
from .access import room_capacity


ROOM_MEDIA_FIELDS = ('episode', 'media_version', 'position', 'playing', 'updated_at')


def reset_room_media(room, episode):
    """Prepare a new source; the caller owns locking and saving the room."""
    room.episode = episode
    room.media_version += 1
    room.position = 0
    room.playing = False
    room.updated_at = timezone.now()
    return ROOM_MEDIA_FIELDS


def room_media_state(room, user):
    episode = room.episode
    published = bool(episode and episode.movie.published and episode.status == 'ready')
    return {
        'episode_id': episode.pk if episode else None,
        'media_version': room.media_version,
        'capacity': room_capacity(room),
        'can_watch': can_watch(user, episode),
        'title': episode.movie.title if published else '',
        'episode_title': episode.title if published else '',
        'player_url': reverse('room_player', args=[room.pk]) + '?' + urlencode({'v': room.media_version}),
    }


def room_player_context(room, user):
    episode = room.episode
    return {
        'room': room, 'episode': episode if episode and episode.movie.published else None,
        'room_capacity': room_capacity(room),
        'is_host': room.host_id == user.pk, 'position': room.position,
        'media_version': room.media_version, 'can_watch_room': can_watch(user, room.episode),
        'room_media': room_media_state(room, user),
        'playlist_url': reverse('room_playlist', args=[room.pk]),
    }
