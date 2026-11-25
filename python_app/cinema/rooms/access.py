"""Room lifetime, membership, presence and admission policies."""

from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import salted_hmac

from ..access import require_watch
from ..models import Membership, Room, RoomPlaylistItem, User


ROOM_LIFETIME = timedelta(hours=6)
ROOM_HEARTBEAT = timedelta(seconds=30)
ROOM_CAPACITY = 10
MAX_ACTIVE_ROOMS = 3


def present_members(room, now=None):
    """The same live roster is used for seat presence and voice discovery."""
    now = timezone.now() if now is None else now
    return room.members.filter(
        banned=False, active=True, user__is_active=True,
        last_seen__gt=now - ROOM_HEARTBEAT,
    )


def room_is_full(room, user):
    return room.members.filter(
        banned=False, active=True, last_seen__gt=timezone.now() - ROOM_HEARTBEAT,
    ).exclude(user=user).count() >= ROOM_CAPACITY


def can_host_room(user):
    return user.is_active and (user.is_vip or user.is_staff)


def create_watch_room(request, episode, form):
    password = form.cleaned_data['password']
    password_hash = make_password(password) if password else ''
    with transaction.atomic():
        host = User.objects.select_for_update().get(pk=request.user.pk)
        if not can_host_room(host):
            raise PermissionDenied('VIP mới có thể tạo phòng.')
        if episode:
            require_watch(host, episode)
        if Room.objects.filter(host=host, closed=False, created_at__gt=timezone.now() - ROOM_LIFETIME).count() >= MAX_ACTIVE_ROOMS:
            return None
        name = request.POST.get('name', '').strip()[:100]
        room = Room.objects.create(
            host=host, episode=episode,
            name=name or (episode.movie.title[:100] if episode else 'Phòng xem của ' + host.username[:80]),
            password_hash=password_hash, requires_approval=form.cleaned_data['requires_approval'],
        )
        Membership.objects.create(room=room, user=host)
        if episode:
            RoomPlaylistItem.objects.create(room=room, episode=episode, position=1)
    return room


def accessible_room(request, pk, lock=False):
    qs = Room.objects.all()
    if lock:
        qs = qs.select_for_update()
    else:
        qs = qs.select_related('episode__movie', 'host')
    room = get_object_or_404(qs, pk=pk, closed=False, created_at__gt=timezone.now() - ROOM_LIFETIME)
    if not can_host_room(room.host):
        raise PermissionDenied('Quyền tạo phòng của chủ phòng đã hết hạn.')
    return room


def active_room_member(request, room):
    return get_object_or_404(Membership, room=room, user=request.user, banned=False, active=True)


def room_member_roster(room):
    members = present_members(room).select_related('user').order_by('user_id')
    return [{
        'user_id': member.user_id,
        'user__username': member.user.username,
        'display_name': member.user.get_full_name().strip() or member.user.username,
        'avatar_url': member.user.avatar.url if member.user.avatar else '',
    } for member in members]


def room_password_attempt_allowed(room_id, user_id):
    key = f'room-password:{room_id}:{user_id}'
    if cache.add(key, 1, timeout=60):
        return True
    try:
        return cache.incr(key) <= 8
    except ValueError:
        return cache.add(key, 1, timeout=60)


def room_access_settings(room):
    version = salted_hmac(
        'cinema.room-access-settings', f'{room.pk}:{room.requires_approval}:{room.password_hash}', algorithm='sha256',
    ).hexdigest()
    return {
        'has_password': bool(room.password_hash),
        'requires_approval': room.requires_approval,
        'settings_version': version,
    }
