"""Host-managed playlists and participant film suggestions."""

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from ..access import require_watch
from ..models import Episode, RoomSuggestion
from ..rooms.access import accessible_room, active_room_member
from ..rooms.media import reset_room_media, room_media_state
from ..rooms.playlist import append_playlist_item, renumber_playlist, room_playlist_state
from ..validation import positive_id


def room_playlist_error(room, user, message, status=400):
    data = {**room_playlist_state(room, user), 'error': message}
    if status == 409:
        data['code'] = 'playlist_changed'
    return JsonResponse(data, status=status)


def playlist_request_id(request, key):
    return positive_id(request.POST.get(key, ''))


@login_required
@require_http_methods(['GET', 'POST'])
def room_playlist(request, pk):
    with transaction.atomic():
        room = accessible_room(request, pk, lock=True)
        active_room_member(request, room)
        if request.method == 'GET':
            return JsonResponse(room_playlist_state(room, request.user))
        action = request.POST.get('action')
        if action != 'suggest':
            if room.host_id != request.user.pk:
                raise PermissionDenied
            if request.POST.get('playlist_version') != str(room.playlist_version):
                return room_playlist_error(room, request.user, 'Danh sách đã thay đổi. Kiểm tra lại rồi thử tiếp.', 409)
        changed = True
        playing = False
        try:
            if action in ('add', 'suggest'):
                episode_id = playlist_request_id(request, 'episode')
                episode = get_object_or_404(Episode.objects.select_related('movie'), pk=episode_id, status='ready', movie__published=True)
                require_watch(request.user, episode)
                if action == 'add':
                    changed = append_playlist_item(room, episode)
                else:
                    existing = room.suggestions.filter(episode=episode).first()
                    if room.playlist_items.filter(episode=episode).exists() or (existing and existing.status == RoomSuggestion.Status.PENDING):
                        changed = False
                    else:
                        pending = room.suggestions.filter(status=RoomSuggestion.Status.PENDING)
                        if pending.count() >= 20 or pending.filter(proposed_by=request.user).count() >= 5:
                            raise ValueError('Đã đủ đề xuất đang chờ. Hãy chờ chủ phòng phản hồi.')
                        if existing:
                            existing.status = RoomSuggestion.Status.PENDING
                            existing.proposed_by = request.user
                            existing.created_at = timezone.now()
                            existing.save(update_fields=['status', 'proposed_by', 'created_at'])
                        else:
                            room.suggestions.create(episode=episode, proposed_by=request.user)
            elif action == 'remove':
                item = get_object_or_404(room.playlist_items, pk=playlist_request_id(request, 'item'))
                item.delete()
                renumber_playlist(room, list(room.playlist_items.values_list('pk', flat=True)))
            elif action == 'reorder':
                try:
                    ordered_ids = json.loads(request.POST.get('item_ids', ''))
                except (ValueError, TypeError, RecursionError):
                    raise ValueError('Thứ tự danh sách không hợp lệ.')
                current_ids = list(room.playlist_items.values_list('pk', flat=True))
                if (
                    not isinstance(ordered_ids, list) or len(ordered_ids) != len(current_ids)
                    or any(type(value) is not int for value in ordered_ids)
                    or set(ordered_ids) != set(current_ids)
                ):
                    raise ValueError('Thứ tự danh sách không hợp lệ.')
                changed = ordered_ids != current_ids
                if changed:
                    renumber_playlist(room, ordered_ids)
            elif action == 'play':
                item = get_object_or_404(room.playlist_items.select_related('episode__movie'), pk=playlist_request_id(request, 'item'))
                require_watch(request.user, item.episode)
                room.save(update_fields=reset_room_media(room, item.episode))
                playing = True
            elif action in ('approve', 'reject'):
                suggestion = get_object_or_404(
                    room.suggestions.select_related('episode__movie'),
                    pk=playlist_request_id(request, 'suggestion'), status=RoomSuggestion.Status.PENDING,
                )
                if action == 'approve':
                    require_watch(request.user, suggestion.episode)
                    append_playlist_item(room, suggestion.episode)
                    suggestion.status = RoomSuggestion.Status.APPROVED
                else:
                    suggestion.status = RoomSuggestion.Status.REJECTED
                suggestion.save(update_fields=['status'])
            else:
                raise ValueError('Thao tác không hợp lệ.')
        except ValueError as error:
            return room_playlist_error(room, request.user, str(error))
        if changed:
            room.playlist_version += 1
            room.save(update_fields=['playlist_version'])
        data = room_playlist_state(room, request.user)
        if playing:
            data.update(room_media_state(room, request.user))
        return JsonResponse(data)
