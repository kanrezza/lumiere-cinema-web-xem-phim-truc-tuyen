"""Playlist serialization and ordered collection operations."""

from django.templatetags.static import static

from ..models import RoomPlaylistItem, RoomSuggestion


def playlist_episode_data(episode):
    if not episode.movie.published or episode.status != 'ready':
        return {
            'episode_id': episode.pk, 'title': 'Phim không còn khả dụng',
            'episode_title': '', 'poster_url': '', 'available': False,
        }
    movie = episode.movie
    if movie.poster:
        poster_url = movie.poster.url
    elif movie.backdrop:
        poster_url = movie.backdrop.url
    elif movie.slug in {'big-buck-bunny', 'orbit', 'dusk', 'forest', 'city', 'ocean', 'summer'}:
        poster_url = static(f'imagery/posters/{movie.slug}.svg')
    else:
        artwork = movie.artwork if movie.artwork in {'orbit', 'dusk', 'forest', 'city', 'ocean', 'summer'} else 'orbit'
        poster_url = static(f'art/{artwork}.svg')
    return {
        'episode_id': episode.pk, 'title': episode.movie.title,
        'episode_title': episode.title, 'poster_url': poster_url, 'available': True,
    }


def room_playlist_state(room, user):
    items = room.playlist_items.select_related('episode__movie').all()
    is_host = room.host_id == user.pk
    suggestions_query = room.suggestions.select_related('episode__movie', 'proposed_by')
    suggestions = list(suggestions_query.filter(status=RoomSuggestion.Status.PENDING))
    if not is_host:
        suggestions.extend(suggestions_query.filter(proposed_by=user).exclude(
            status=RoomSuggestion.Status.PENDING,
        ).order_by('-created_at', '-pk')[:20])
    return {
        'playlist_version': room.playlist_version, 'is_host': is_host, 'can_manage': is_host,
        'items': [dict(id=item.pk, position=item.position, **playlist_episode_data(item.episode)) for item in items],
        'suggestions': [dict(
            id=entry.pk, proposed_by=entry.proposed_by.username, proposer_id=entry.proposed_by_id,
            status=entry.status, **playlist_episode_data(entry.episode),
        ) for entry in suggestions],
    }


def append_playlist_item(room, episode):
    existing = room.playlist_items.filter(episode=episode).first()
    if existing:
        return False
    count = room.playlist_items.count()
    if count >= 50:
        raise ValueError('Danh sách đã đủ 50 tập phim.')
    last_position = room.playlist_items.order_by('-position').values_list('position', flat=True).first() or 0
    room.playlist_items.create(episode=episode, position=last_position + 1)
    return True


def renumber_playlist(room, ordered_ids):
    positions = {pk: index for index, pk in enumerate(ordered_ids, 1)}
    items = list(room.playlist_items.all())
    for item in items:
        item.position = positions[item.pk]
    RoomPlaylistItem.objects.bulk_update(items, ['position'])
