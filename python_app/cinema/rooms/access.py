"""Room lifetime, membership, presence and admission policies."""

from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import salted_hmac

from ..access import require_watch
from ..models import Membership, Room, RoomPlaylistItem, RoomVoiceSignal, User
from .identity import room_user_profile


ROOM_LIFETIME = timedelta(hours=6)
ROOM_HEARTBEAT = timedelta(seconds=30)
FREE_ROOM_CAPACITY = 3
VIP_ROOM_CAPACITY = 10
MAX_ACTIVE_ROOMS = 3


def host_capacity(user):
    return VIP_ROOM_CAPACITY if user.is_vip or user.is_staff else FREE_ROOM_CAPACITY


def room_capacity(room):
    return host_capacity(room.host)


def present_members(room, now=None):
    """The same live roster is used for seat presence and voice discovery."""
    now = timezone.now() if now is None else now
    return room.members.filter(
        banned=False, active=True, user__is_active=True,
        last_seen__gt=now - ROOM_HEARTBEAT,
    )


def _present_guests(room, now=None):
    return present_members(room, now).exclude(user_id=room.host_id).order_by('pk')


def admitted_members(room, now=None):
    """Reserve one host seat; retain the earliest guests if the plan shrinks."""
    guest_ids = list(_present_guests(room, now).values_list('pk', flat=True)[:room_capacity(room) - 1])
    return present_members(room, now).filter(Q(user_id=room.host_id) | Q(pk__in=guest_ids))


def enforce_room_capacity(room):
    """Called under the room row lock; release excess seats without banning."""
    removed = list(_present_guests(room).values_list('pk', 'user_id')[room_capacity(room) - 1:])
    if removed:
        member_ids, user_ids = zip(*removed)
        room.members.filter(pk__in=member_ids).update(
            active=False, voice_session=None, voice_seen_at=None, voice_mic_on=False,
        )
        RoomVoiceSignal.objects.filter(room=room).filter(
            Q(sender_id__in=user_ids) | Q(recipient_id__in=user_ids),
        ).delete()


def room_is_full(room, user):
    if user.pk == room.host_id:
        return False
    guests = list(_present_guests(room).values_list('user_id', flat=True)[:room_capacity(room) - 1])
    return user.pk not in guests and len(guests) >= room_capacity(room) - 1


def room_full_message(room):
    return f'Phòng đã đủ {room_capacity(room)} người, tính cả chủ phòng.'


def can_host_room(user):
    return user.is_authenticated and user.is_active


def create_watch_room(request, episode, form):
    password = form.cleaned_data['password']
    password_hash = make_password(password) if password else ''
    with transaction.atomic():
        host = User.objects.select_for_update().get(pk=request.user.pk)
        if not can_host_room(host):
            raise PermissionDenied('Tài khoản không còn hoạt động.')
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
        raise PermissionDenied('Chủ phòng hiện không thể sử dụng phòng xem.')
    if lock:
        enforce_room_capacity(room)
    return room


def active_room_member(request, room):
    member = get_object_or_404(Membership, room=room, user=request.user, banned=False, active=True)
    if room_is_full(room, request.user):
        raise PermissionDenied(room_full_message(room))
    return member


def room_member_roster(room):
    members = admitted_members(room).select_related('user').order_by('user_id')
    return [{
        'user_id': member.user_id,
        'user__username': member.user.username,
        **room_user_profile(member.user),
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
