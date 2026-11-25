"""Playback access policy shared by streaming, captions and watch rooms."""

from django.core.exceptions import PermissionDenied


def can_watch(user, episode):
    return bool(episode and user.is_authenticated and user.is_active and episode.movie.published and episode.status == 'ready' and (not episode.movie.is_vip or user.is_vip or user.is_staff))


def require_watch(user, episode):
    if not can_watch(user, episode): raise PermissionDenied('Bạn chưa có quyền xem hoặc video chưa sẵn sàng.')
