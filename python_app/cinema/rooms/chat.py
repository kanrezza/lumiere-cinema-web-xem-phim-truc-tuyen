"""Chronological room messages with public author profiles."""

from ..models import Chat
from .identity import room_user_profile


def room_messages(room):
    latest = list(Chat.objects.filter(room=room).select_related('user').order_by('-id')[:60])
    return [
        {
            'id': entry.pk, 'user_id': entry.user_id, 'user': entry.user.username,
            'content': entry.content, **room_user_profile(entry.user),
        }
        for entry in reversed(latest)
    ]
