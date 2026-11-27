"""Register Lumière's model admins and preserve their public import paths.

Implementations live in admin_components; this module is the single registration
entry point used by Django's admin autodiscovery.
"""
from django.contrib import admin

from .admin_components.catalog import ActorAdmin, CategoryAdmin, EpisodeAdmin, MovieAdmin
from .admin_components.common import LocalizedAdminMixin
from .admin_components.community import CommentAdmin, CommunityAdmin, RatingAdmin, RoomAdmin
from .admin_components.filters import (
    CommentDateFilter, CommunityMovieFilter, CommunityRatingFilter,
    CommunityRoomMovieFilter, ModerationReasonFilter,
)
from .admin_components.membership import CustomUserAdmin, OrderAdmin, PlanAdmin
from .admin_components.reports import ReportAdmin
from .admin_components.premieres import PremiereAdmin, PremiereMessageAdmin
from .admin_components.subtitles import SubtitleAdmin, SubtitleAdminForm
from .models import Actor, Category, Comment, Episode, Movie, Order, Plan, Premiere, PremiereMessage, Rating, Report, Room, Subtitle, User

__all__ = [
    'ActorAdmin', 'CategoryAdmin', 'CommentAdmin', 'CommentDateFilter', 'CommunityAdmin',
    'CommunityMovieFilter', 'CommunityRatingFilter', 'CommunityRoomMovieFilter',
    'CustomUserAdmin', 'EpisodeAdmin', 'LocalizedAdminMixin', 'ModerationReasonFilter',
    'MovieAdmin', 'OrderAdmin', 'PlanAdmin', 'RatingAdmin', 'ReportAdmin', 'RoomAdmin',
    'SubtitleAdmin', 'SubtitleAdminForm',
]

for model, model_admin in (
    (User, CustomUserAdmin),
    (Movie, MovieAdmin),
    (Episode, EpisodeAdmin),
    (Subtitle, SubtitleAdmin),
    (Order, OrderAdmin),
    (Category, CategoryAdmin),
    (Actor, ActorAdmin),
    (Comment, CommentAdmin),
    (Rating, RatingAdmin),
    (Report, ReportAdmin),
    (Plan, PlanAdmin),
    (Room, RoomAdmin),
    (Premiere, PremiereAdmin),
    (PremiereMessage, PremiereMessageAdmin),
):
    admin.site.register(model, model_admin)

admin.site.site_header = 'Lumière • Quản trị'
admin.site.site_title = 'Lumière Studio'
