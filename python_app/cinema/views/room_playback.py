"""Room film selection and synchronized playback/chat endpoint."""

import math
from contextlib import nullcontext

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.vary import vary_on_headers

from ..access import require_watch
from ..models import Chat, Episode, Membership, Movie, RoomVoiceSignal
from ..rooms.access import accessible_room, active_room_member, room_is_full, room_member_roster
from ..rooms.media import reset_room_media, room_media_state
from ..search import filter_movie_search
from ..validation import positive_id


@login_required
@require_http_methods(['GET', 'POST'])
@vary_on_headers('X-Lumiere-Room-Selection')
def room_selection(request, pk):
    with transaction.atomic() if request.method == 'POST' else nullcontext():
        room = accessible_room(request, pk, lock=request.method == 'POST')
        active_room_member(request, room)
        if request.method == 'POST':
            if room.host_id != request.user.pk:
                raise PermissionDenied
            if request.POST.get('media_version') != str(room.media_version):
                return JsonResponse({
                    **room_media_state(room, request.user), 'code': 'media_changed',
                    'error': 'Phim trong phòng đã thay đổi. Kiểm tra lại rồi chọn phim.',
                }, status=409)
            action = request.POST.get('action', 'select')
            episode = None
            if action == 'select':
                episode_id = positive_id(request.POST.get('episode', ''))
                if episode_id is None:
                    return JsonResponse({'error': 'Tập phim không hợp lệ.'}, status=400)
                episode = get_object_or_404(Episode.objects.select_related('movie'), pk=episode_id, status='ready', movie__published=True)
                require_watch(request.user, episode)
            elif action != 'clear':
                return JsonResponse({'error': 'Thao tác không hợp lệ.'}, status=400)
            room.save(update_fields=reset_room_media(room, episode))
            if request.headers.get('X-Lumiere-Room-Selection') == '1':
                return JsonResponse(room_media_state(room, request.user))
            return redirect('room', pk=room.pk)

        query = request.GET.get('q', '').strip()[:150]
        movies = filter_movie_search(Movie.objects.filter(published=True), query)
        episodes = Episode.objects.select_related('movie').filter(movie__in=movies, status='ready')
        if not (request.user.is_vip or request.user.is_staff):
            episodes = episodes.filter(movie__is_vip=False)
        context = {
            'room': room, 'q': query, 'is_host': room.host_id == request.user.pk,
            'episodes': Paginator(episodes.order_by('movie__title', 'movie_id', 'number', 'pk'), 12).get_page(request.GET.get('page')),
        }
        template = 'cinema/room_selection_results.html' if request.headers.get('X-Lumiere-Room-Selection') == '1' else 'cinema/room_selection.html'
        return render(request, template, context)


@login_required
@require_http_methods(['GET', 'POST'])
def room_state(request, pk):
    with transaction.atomic():
        room = accessible_room(request, pk, lock=True)
        member = get_object_or_404(Membership, room=room, user=request.user, banned=False, active=True)
        if room_is_full(room, request.user):
            return JsonResponse({'error': 'Phòng đã đủ 10 thành viên.'}, status=409)
        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'chat':
                content = request.POST.get('content', '').strip()
                if not 1 <= len(content) <= 500: return JsonResponse({'error': 'Tin nhắn cần 1–500 ký tự.'}, status=400)
                Chat.objects.create(room=room, user=request.user, content=content)
            else:
                if room.host_id != request.user.pk: raise PermissionDenied
                if action == 'close':
                    room.closed = True
                    room.members.update(voice_session=None, voice_seen_at=None, voice_mic_on=False)
                    RoomVoiceSignal.objects.filter(room=room).delete()
                elif action == 'kick':
                    target = positive_id(request.POST.get('user', ''))
                    if target is None:
                        return JsonResponse({'error': 'Thành viên không hợp lệ'}, status=400)
                    removed = Membership.objects.filter(room=room, user_id=target, banned=False).exclude(user=room.host).update(
                        banned=True, active=False, voice_session=None, voice_seen_at=None, voice_mic_on=False,
                    )
                    if removed:
                        RoomVoiceSignal.objects.filter(room=room).filter(Q(sender_id=target) | Q(recipient_id=target)).delete()
                elif action == 'sync':
                    version = request.POST.get('media_version')
                    if version != str(room.media_version) and not (version is None and room.media_version == 1):
                        return JsonResponse({
                            **room_media_state(room, request.user), 'code': 'media_changed',
                            'error': 'Phim trong phòng đã thay đổi. Đang cập nhật nguồn phát.',
                        }, status=409)
                    if not room.episode:
                        return JsonResponse({'error': 'Chọn phim trước khi bắt đầu phát.'}, status=400)
                    require_watch(request.user, room.episode)
                    try: position = float(request.POST.get('position', 0))
                    except ValueError: return JsonResponse({'error': 'Vị trí không hợp lệ'}, status=400)
                    if not math.isfinite(position) or not 0 <= position <= room.episode.duration + 1: return JsonResponse({'error': 'Vị trí không hợp lệ'}, status=400)
                    room.position = position
                    room.playing = request.POST.get('playing') == 'true'
                    room.updated_at = timezone.now()
                else: return JsonResponse({'error': 'Thao tác không hợp lệ'}, status=400)
                room.save()
        member.last_seen = timezone.now()
        member.save(update_fields=['last_seen'])
        position = min(room.episode.duration, room.position + ((timezone.now() - room.updated_at).total_seconds() if room.playing else 0)) if room.episode else 0
        chats = list(Chat.objects.filter(room=room).select_related('user').order_by('-id')[:60])
        return JsonResponse({**room_media_state(room, request.user), 'position': position, 'playing': bool(room.episode and room.playing), 'closed': room.closed, 'members': room_member_roster(room), 'messages': [{'id': c.pk, 'user_id': c.user_id, 'user': c.user.username, 'content': c.content} for c in reversed(chats)]})
