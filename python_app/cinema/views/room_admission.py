"""Password-protected joining and host approval endpoints."""

from contextlib import nullcontext

from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods

from ..forms import RoomAccessForm
from ..models import Membership, RoomJoinRequest
from ..validation import positive_id
from ..rooms.access import accessible_room, room_access_settings, room_is_full, room_password_attempt_allowed


def room_lobby(request, room, error='', status=200):
    join_status = RoomJoinRequest.objects.filter(room=room, user=request.user).values_list('status', flat=True).first()
    return render(request, 'cinema/join.html', {'room': room, 'join_status': join_status, 'join_error': error}, status=status)


@login_required
@require_POST
def join_room(request, pk):
    with transaction.atomic():
        room = accessible_room(request, pk, lock=True)
        member = Membership.objects.filter(room=room, user=request.user).first()
        if member and member.banned: raise PermissionDenied
        if member and member.active:
            return redirect('room', pk=pk)
        admission = RoomJoinRequest.objects.filter(room=room, user=request.user).first()
        if admission and admission.status == RoomJoinRequest.Status.REJECTED:
            return room_lobby(request, room, status=403)
        if room.requires_approval and admission and admission.status == RoomJoinRequest.Status.PENDING:
            return redirect('room', pk=pk)
        approved = admission and admission.status == RoomJoinRequest.Status.APPROVED
        if room.password_hash and not approved:
            if not room_password_attempt_allowed(room.pk, request.user.pk):
                return room_lobby(request, room, 'Bạn đã thử quá nhiều lần. Hãy đợi một phút.', 429)
            password = request.POST.get('password', '')
            if not 4 <= len(password) <= 128 or not check_password(password, room.password_hash):
                return room_lobby(request, room, 'Mật khẩu phòng không đúng.', 400)
        if room.requires_approval and not approved:
            RoomJoinRequest.objects.get_or_create(room=room, user=request.user)
            return redirect('room', pk=pk)
        if room_is_full(room, request.user):
            return room_lobby(request, room, 'Phòng đã đủ 10 thành viên.', 409)
        Membership.objects.update_or_create(room=room, user=request.user, defaults={
            'active': True, 'last_seen': timezone.now(), 'voice_session': None, 'voice_seen_at': None, 'voice_mic_on': False,
        })
        if admission:
            admission.delete()
    return redirect('room', pk=pk)


@login_required
@require_http_methods(['GET', 'POST'])
def room_admission(request, pk):
    with transaction.atomic() if request.method == 'POST' else nullcontext():
        room = accessible_room(request, pk, lock=request.method == 'POST')
        if room.host_id != request.user.pk:
            if request.method != 'GET':
                raise PermissionDenied
            status = room.join_requests.filter(user=request.user).values_list('status', flat=True).first()
            return JsonResponse({'status': status, 'requires_approval': room.requires_approval})
        if request.method == 'POST':
            action = request.POST.get('action')
            if action in ('approve', 'reject'):
                entry_id = positive_id(request.POST.get('request', ''))
                if entry_id is None:
                    return JsonResponse({'error': 'Yêu cầu vào phòng không hợp lệ.'}, status=400)
                entry = get_object_or_404(room.join_requests, pk=entry_id, status=RoomJoinRequest.Status.PENDING)
                entry.status = RoomJoinRequest.Status.APPROVED if action == 'approve' else RoomJoinRequest.Status.REJECTED
                entry.save(update_fields=['status'])
            elif action == 'settings':
                current_settings = room_access_settings(room)
                if request.POST.get('settings_version') != current_settings['settings_version']:
                    return JsonResponse({
                        **current_settings,
                        'error': 'Cài đặt phòng đã thay đổi. Kiểm tra lại rồi bấm lưu.',
                    }, status=409)
                form = RoomAccessForm(request.POST)
                remove_password = request.POST.get('remove_password') == 'on'
                if not form.is_valid() or (remove_password and form.cleaned_data['password']):
                    return JsonResponse({'error': 'Nhập mật khẩu mới từ 4 đến 128 ký tự hoặc chọn bỏ mật khẩu.'}, status=400)
                password = form.cleaned_data['password']
                if password or remove_password:
                    room.password_hash = make_password(password) if password else ''
                    room.join_requests.exclude(status=RoomJoinRequest.Status.REJECTED).delete()
                room.requires_approval = form.cleaned_data['requires_approval']
                room.save(update_fields=['password_hash', 'requires_approval'])
            else:
                return JsonResponse({'error': 'Thao tác không hợp lệ.'}, status=400)
        pending = room.join_requests.filter(status=RoomJoinRequest.Status.PENDING).order_by('created_at', 'pk')
        return JsonResponse({
            **room_access_settings(room),
            'pending': list(pending.values('pk', 'user__username')[:30]), 'pending_count': pending.count(),
        })
