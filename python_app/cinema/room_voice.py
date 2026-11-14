"""Room-scoped signaling and microphone permissions for browser voice chat."""

import json
from datetime import timedelta
from uuid import UUID, uuid4

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Membership, RoomVoiceSignal
from .views import accessible_room


ROOM_HEARTBEAT = timedelta(seconds=30)
VOICE_HEARTBEAT = timedelta(seconds=20)
VOICE_REFRESH = timedelta(seconds=6)
SIGNAL_TTL = timedelta(seconds=45)
MAX_SIGNALS_PER_TARGET = 128
MAX_SDP_LENGTH = 16_384
MAX_INTEGER_ID = (1 << 63) - 1


def eligible_members(room, now):
    members = room.members.filter(
        active=True, banned=False, last_seen__gt=now - ROOM_HEARTBEAT, user__is_active=True,
    )
    if room.episode.movie.is_vip:
        members = members.filter(Q(user__is_staff=True) | Q(user__vip_until__gt=now))
    return members


def voice_session(member, now):
    if member.voice_seen_at and member.voice_seen_at > now - VOICE_HEARTBEAT:
        return member.voice_session
    return None


def member_state(member, now):
    session = voice_session(member, now)
    return {
        'user_id': member.user_id,
        'voice_session': session,
        'host_muted': member.voice_host_muted,
        'mic_on': bool(session and member.voice_mic_on and not member.voice_host_muted),
    }


def integer_id(value, default=None):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if 0 <= value <= MAX_INTEGER_ID else default


def uuid_value(value):
    try:
        return UUID(value)
    except (TypeError, ValueError, AttributeError):
        return None


def error(message, status=400):
    return JsonResponse({'error': message}, status=status)


@login_required
@require_GET
def state(request, pk):
    room = accessible_room(request, pk)
    now = timezone.now()
    requested_session = uuid_value(request.GET.get('session'))
    members = eligible_members(room, now)
    # On page load the video poll may not have refreshed the member's presence yet.
    if requested_session is None:
        me = get_object_or_404(Membership, room=room, user=request.user, active=True, banned=False)
    else:
        me = get_object_or_404(members, user=request.user)
    current_session = voice_session(me, now) if requested_session else None
    peers = list(members.exclude(pk=me.pk).order_by('user_id'))
    signals = []
    if current_session and current_session == requested_session:
        if me.voice_seen_at < now - VOICE_REFRESH:
            members.filter(pk=me.pk, voice_session=current_session, voice_seen_at=me.voice_seen_at).update(voice_seen_at=now)
        peer_sessions = {peer.user_id: voice_session(peer, now) for peer in peers}
        after = integer_id(request.GET.get('after', '0'), 0)
        pending = RoomVoiceSignal.objects.filter(
            room=room, recipient=request.user, recipient_session=current_session, id__gt=after, expires_at__gt=now,
        ).order_by('id')[:MAX_SIGNALS_PER_TARGET]
        signals = [
            {'id': signal.id, 'from_user_id': signal.sender_id, 'from_session': signal.sender_session,
             'type': signal.kind, 'payload': signal.payload}
            for signal in pending if peer_sessions.get(signal.sender_id) == signal.sender_session
        ]
    self_state = member_state(me, now)
    if me.last_seen <= now - ROOM_HEARTBEAT:
        self_state.update(voice_session=None, mic_on=False)
    return JsonResponse({
        'self': self_state,
        'peers': [member_state(peer, now) for peer in peers],
        'signals': signals,
        'ice_servers': settings.ROOM_VOICE_ICE_SERVERS,
    })


def valid_signal_payload(kind, payload):
    if kind not in ('offer', 'answer') or not isinstance(payload, dict):
        return False
    sdp = payload.get('sdp')
    if not isinstance(sdp, str) or len(sdp) > MAX_SDP_LENGTH or not sdp.startswith('v=0'):
        return False
    # Exchange a single audio transceiver and no camera or data channels.
    media = [line for line in sdp.splitlines() if line.startswith('m=')]
    return (
        len(media) == 1 and media[0].startswith('m=audio ')
        and set(payload) == {'sdp', 'negotiation'}
        and uuid_value(payload['negotiation']) is not None
    )


def relay_signal(request, me, members, room, now):
    kind = request.POST.get('type')
    raw_payload = request.POST.get('payload', '')
    if len(raw_payload) > 2 * MAX_SDP_LENGTH:
        return error('Tín hiệu trò chuyện thoại không hợp lệ.')
    try:
        payload = json.loads(raw_payload)
    except (ValueError, RecursionError):
        return error('Tín hiệu trò chuyện thoại không hợp lệ.')
    if not valid_signal_payload(kind, payload):
        return error('Tín hiệu trò chuyện thoại không hợp lệ.')
    recipient_id = integer_id(request.POST.get('user'))
    recipient_session = uuid_value(request.POST.get('target_session'))
    recipient = members.exclude(pk=me.pk).filter(user_id=recipient_id, voice_session=recipient_session).first()
    if not recipient_session or not recipient or voice_session(recipient, now) != recipient_session:
        return error('Thành viên không còn trong cuộc trò chuyện thoại.', 409)
    if (kind == 'offer') != (me.user_id < recipient.user_id):
        return error('Vai trò gửi tín hiệu không hợp lệ.')

    queue = RoomVoiceSignal.objects.filter(room=room, recipient_id=recipient_id, recipient_session=recipient_session)
    RoomVoiceSignal.objects.filter(expires_at__lte=now).delete()
    queue.create(
        room=room, recipient_id=recipient_id, recipient_session=recipient_session,
        sender_id=me.user_id, sender_session=me.voice_session,
        kind=kind, payload=payload, expires_at=now + SIGNAL_TTL,
    )
    old_ids = list(queue.order_by('-id').values_list('pk', flat=True)[MAX_SIGNALS_PER_TARGET:])
    if old_ids:
        queue.filter(pk__in=old_ids).delete()
    return JsonResponse({'ok': True})


@login_required
@require_POST
def command(request, pk):
    with transaction.atomic():
        room = accessible_room(request, pk, lock=True)
        now = timezone.now()
        members = eligible_members(room, now)
        me = get_object_or_404(members, user=request.user)
        action = request.POST.get('action')

        if action == 'join':
            me.voice_session = uuid4()
            me.voice_seen_at = now
            me.voice_mic_on = False
            me.save(update_fields=['voice_session', 'voice_seen_at', 'voice_mic_on'])
            RoomVoiceSignal.objects.filter(room=room).filter(Q(sender_id=me.user_id) | Q(recipient_id=me.user_id)).delete()
            return JsonResponse({'session': me.voice_session})

        if action == 'mute':
            if room.host_id != me.user_id:
                raise PermissionDenied
            muted = request.POST.get('muted')
            user_id = integer_id(request.POST.get('user'))
            if muted not in ('true', 'false') or not user_id or user_id == me.user_id:
                return error('Thao tác tắt mic không hợp lệ.')
            target = get_object_or_404(members, user_id=user_id)
            target.voice_host_muted = muted == 'true'
            if target.voice_host_muted:
                target.voice_mic_on = False
            target.save(update_fields=['voice_host_muted', 'voice_mic_on'])
            return JsonResponse({'ok': True})

        if action not in ('leave', 'mic', 'signal'):
            return error('Thao tác trò chuyện thoại không hợp lệ.')
        requested_session = uuid_value(request.POST.get('session'))
        if not requested_session or requested_session != voice_session(me, now):
            return error('Phiên trò chuyện thoại đã kết thúc. Hãy vào lại.', 409)

        if action == 'signal':
            return relay_signal(request, me, members, room, now)
        if action == 'mic':
            enabled = request.POST.get('enabled')
            if enabled not in ('true', 'false'):
                return error('Trạng thái mic không hợp lệ.')
            if enabled == 'true' and me.voice_host_muted:
                return error('Chủ phòng đang tắt mic của bạn.', 403)
            me.voice_mic_on = enabled == 'true'
            me.save(update_fields=['voice_mic_on'])
        else:
            me.voice_session = None
            me.voice_seen_at = None
            me.voice_mic_on = False
            me.save(update_fields=['voice_session', 'voice_seen_at', 'voice_mic_on'])
            RoomVoiceSignal.objects.filter(room=room).filter(Q(sender_id=me.user_id) | Q(recipient_id=me.user_id)).delete()
        return JsonResponse({'ok': True})
