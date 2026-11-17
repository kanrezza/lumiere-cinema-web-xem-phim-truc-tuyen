"""Account erasure without destroying payment reconciliation records."""
import uuid

from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from .avatars import is_managed_avatar
from .models import (
    Chat, Comment, ErasureRequest, History, Membership, Rating, Report, Room,
    RoomJoinRequest, RoomVoiceSignal, SubtitleTranscription, SubtitleTranslation,
    User, Watchlist,
)

NOTICE_VERSION = '2026-11-17'


def _lock_viewer(user_id):
    user = User.objects.select_for_update().get(pk=user_id)
    if not user.is_active or user.is_staff or user.is_superuser or user.erased_at:
        raise PermissionDenied
    return user


@transaction.atomic
@sensitive_variables('password')
def request_erasure(user_id, password):
    user = _lock_viewer(user_id)
    if not user.check_password(password):
        raise ValidationError('Mật khẩu hiện tại không đúng.')
    pending = user.erasure_requests.filter(status=ErasureRequest.Status.PENDING).first()
    return pending or user.erasure_requests.create(notice_version=NOTICE_VERSION)


@transaction.atomic
def cancel_erasure(user_id):
    user = _lock_viewer(user_id)
    user.erasure_requests.filter(status=ErasureRequest.Status.PENDING).update(
        status=ErasureRequest.Status.CANCELLED, resolved_at=timezone.now(),
    )


def cleanup_avatar(erasure_id):
    erasure = ErasureRequest.objects.get(pk=erasure_id)
    name = erasure.avatar_pending
    if not is_managed_avatar(name):
        return
    if not User.objects.filter(avatar=name).exists():
        User._meta.get_field('avatar').storage.delete(name)
    ErasureRequest.objects.filter(pk=erasure_id, avatar_pending=name).update(avatar_pending='')


@transaction.atomic
def complete_erasure(erasure_id, reviewer):
    if not (reviewer.is_active and reviewer.is_staff and reviewer.is_superuser):
        raise PermissionDenied
    reference = ErasureRequest.objects.get(pk=erasure_id)
    user = User.objects.select_for_update().get(pk=reference.user_id)
    erasure = ErasureRequest.objects.select_for_update().get(pk=erasure_id)
    if erasure.status != ErasureRequest.Status.PENDING:
        raise ValidationError('Yêu cầu đã được xử lý hoặc hủy.')
    if user.is_staff or user.is_superuser or user.erased_at:
        raise ValidationError('Tài khoản này cần được xử lý qua quy trình quản trị riêng.')

    Room.objects.filter(host=user).delete()
    for model in (Watchlist, History, Comment, Rating, Report, RoomJoinRequest, Membership, Chat):
        model.objects.filter(user=user).delete()
    RoomVoiceSignal.objects.filter(Q(sender=user) | Q(recipient=user)).delete()
    for model in (SubtitleTranslation, SubtitleTranscription):
        model.objects.filter(requested_by=user).update(requested_by=None)
    LogEntry.objects.filter(content_type=ContentType.objects.get_for_model(User), object_id=str(user.pk)).update(
        object_repr='Tài khoản đã ẩn danh', change_message='',
    )

    avatar_name = user.avatar.name
    identity = uuid.uuid4().hex
    now = timezone.now()
    user.username = f'erased_{identity}'
    user.email = f'{identity}@erased.invalid'
    user.first_name = user.last_name = user.bio = user.avatar = ''
    user.is_active = False
    user.vip_until = user.last_login = None
    user.erased_at = now
    user.set_unusable_password()
    user.groups.clear()
    user.user_permissions.clear()
    user.save(update_fields=(
        'username', 'email', 'first_name', 'last_name', 'bio', 'avatar', 'is_active',
        'vip_until', 'last_login', 'erased_at', 'password',
    ))

    erasure.status = ErasureRequest.Status.COMPLETED
    erasure.reviewed_by = reviewer
    erasure.resolved_at = now
    erasure.avatar_pending = avatar_name if is_managed_avatar(avatar_name) else ''
    erasure.save(update_fields=('status', 'reviewed_by', 'resolved_at', 'avatar_pending'))
    if erasure.avatar_pending:
        transaction.on_commit(lambda: cleanup_avatar(erasure_id), robust=True)
    return erasure
