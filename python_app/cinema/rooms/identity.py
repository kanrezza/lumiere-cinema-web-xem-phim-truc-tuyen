"""Public profile fields shared by room seats and chat messages."""


def room_user_profile(user):
    return {
        'display_name': user.get_full_name().strip() or user.username,
        'avatar_url': user.avatar.url if user.avatar else '',
    }
