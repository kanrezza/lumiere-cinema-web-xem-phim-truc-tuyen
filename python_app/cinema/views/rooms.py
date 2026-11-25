"""Persistent room creation, room pages and leaving a screening."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from ..access import require_watch
from ..forms import RoomAccessForm
from ..models import Episode, Membership, Room, RoomVoiceSignal
from ..rooms.access import ROOM_LIFETIME, accessible_room, active_room_member, can_host_room, create_watch_room, room_access_settings
from ..rooms.media import room_player_context
from .room_admission import room_lobby


@login_required
@require_http_methods(['GET', 'POST'])
def rooms(request):
    form = RoomAccessForm(request.POST if request.method == 'POST' else None)
    error = ''
    if request.method == 'POST':
        if not can_host_room(request.user):
            raise PermissionDenied('VIP mới có thể tạo phòng.')
        if form.is_valid():
            created = create_watch_room(request, None, form)
            if created:
                return redirect('room', pk=created.pk)
            error = 'Bạn đã có 3 phòng đang hoạt động.'
    available = Room.objects.filter(
        Q(host=request.user) | Q(members__user=request.user, members__banned=False, members__active=True),
        closed=False, created_at__gt=timezone.now() - ROOM_LIFETIME,
    ).select_related('host', 'episode__movie').distinct().order_by('-created_at')
    return render(request, 'cinema/rooms.html', {
        'rooms': available, 'form': form, 'can_create_room': can_host_room(request.user), 'error': error,
    }, status=400 if request.method == 'POST' else 200)


@login_required
@require_POST
def create_room(request, pk):
    episode = get_object_or_404(Episode.objects.select_related('movie'), pk=pk)
    require_watch(request.user, episode)
    if not can_host_room(request.user):
        raise PermissionDenied('VIP mới có thể tạo phòng.')
    form = RoomAccessForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Mật khẩu phòng cần từ 4 đến 128 ký tự.')
        return redirect(reverse('watch', args=[pk]) + '#watch-together')
    created = create_watch_room(request, episode, form)
    if not created:
        messages.error(request, 'Bạn đã có 3 phòng đang hoạt động.')
        return redirect('watch', pk=pk)
    return redirect('room', pk=created.pk)


@login_required
@require_GET
def room_player(request, pk):
    room = accessible_room(request, pk)
    active_room_member(request, room)
    response = render(request, 'cinema/room_player.html', room_player_context(room, request.user))
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
def room(request, pk):
    room = accessible_room(request, pk)
    member = Membership.objects.filter(room=room, user=request.user).first()
    if member and member.banned:
        raise PermissionDenied('Bạn đã bị loại khỏi phòng.')
    if not member or not member.active:
        return room_lobby(request, room)
    response = render(request, 'cinema/room.html', {
        **room_player_context(room, request.user),
        'room_access_version': room_access_settings(room)['settings_version'] if room.host_id == request.user.pk else '',
    })
    response.allow_room_microphone = True
    return response


@login_required
@require_POST
def leave_room(request, pk):
    with transaction.atomic():
        room = get_object_or_404(Room.objects.select_for_update(), pk=pk)
        members = room.members.all()
        signals = RoomVoiceSignal.objects.filter(room=room)
        if room.host_id == request.user.pk:
            room.closed = True
            room.save(update_fields=['closed'])
        else:
            members = members.filter(user=request.user)
            signals = signals.filter(Q(sender=request.user) | Q(recipient=request.user))
        members.update(active=False, voice_session=None, voice_seen_at=None, voice_mic_on=False)
        signals.delete()
    return redirect('library')
