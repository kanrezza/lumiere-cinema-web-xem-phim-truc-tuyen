"""Public endpoint exports; implementations live in focused feature modules.

The explicit exports keep URL configuration and existing Python imports stable.
Shared access checks and queries are implemented outside the view layer.
"""

from ..access import can_watch, require_watch
from ..queries import catalog_movies, public_country_groups
from ..rooms.access import accessible_room
from .accounts import profile, profile_avatar, register
from .catalog import catalog, landing
from .community import comment, delete_comment, rate, watchlist_toggle
from .dashboard import studio
from .discovery import actor_detail, actors, categories, countries
from .library import clear_history, hide_continue, library
from .membership import checkout, ipn, payment_return, plans
from .movies import movie_detail, movie_trailer
from .playback import progress, report, stream, stream_ticket, watch
from .room_admission import join_room, room_admission
from .room_playback import room_selection, room_state
from .room_playlist import room_playlist
from .rooms import create_room, leave_room, room, room_player, rooms

__all__ = [
    'accessible_room', 'actor_detail', 'actors', 'can_watch', 'catalog', 'catalog_movies',
    'categories', 'checkout', 'clear_history', 'comment', 'countries', 'create_room',
    'delete_comment', 'hide_continue', 'ipn', 'join_room', 'landing', 'leave_room',
    'library', 'movie_detail', 'movie_trailer', 'payment_return', 'plans', 'profile',
    'profile_avatar', 'progress', 'public_country_groups', 'rate', 'register',
    'report', 'require_watch', 'room', 'room_admission', 'room_player', 'room_playlist',
    'room_selection', 'room_state', 'rooms', 'stream', 'stream_ticket', 'studio',
    'watch', 'watchlist_toggle',
]
