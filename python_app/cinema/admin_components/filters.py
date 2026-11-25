"""Community changelist filters shared by comments, ratings and rooms."""
from django.contrib import admin

from ..models import Comment, Movie


class CommunityMovieFilter(admin.SimpleListFilter):
    title = 'Phim'
    parameter_name = 'movie'
    template = 'admin/community_filter.html'
    movie_field = 'movie'

    def lookups(self, request, model_admin):
        title = f'{self.movie_field}__title'
        key = f'{self.movie_field}__pk'
        rows = model_admin.get_queryset(request).order_by(title, key)
        choices = dict(Movie.objects.filter(published=True).values_list('pk', 'title'))
        choices.update((pk, name) for pk, name in rows.values_list(key, title).distinct() if pk is not None and name is not None)
        return sorted(choices.items(), key=lambda item: (item[1].casefold(), item[0]))

    def queryset(self, request, queryset):
        if self.value() and any(str(pk) == self.value() for pk, _ in self.lookup_choices):
            return queryset.filter(**{f'{self.movie_field}__pk': self.value()})
        return queryset


class CommunityRoomMovieFilter(CommunityMovieFilter):
    movie_field = 'episode__movie'


class ModerationReasonFilter(admin.SimpleListFilter):
    title = 'Lý do gắn cờ'
    parameter_name = 'moderation_reason'
    template = 'admin/community_filter.html'

    def lookups(self, request, model_admin):
        return Comment.Reason.choices

    def queryset(self, request, queryset):
        reason = self.value()
        if reason in Comment.Reason.values:
            return queryset.filter(moderation_matches__has_key=reason)
        return queryset


class CommunityRatingFilter(admin.SimpleListFilter):
    title = 'Điểm đánh giá'
    parameter_name = 'score'
    template = 'admin/community_filter.html'

    def lookups(self, request, model_admin):
        return [(score, f'{score} / 5') for score in range(1, 6)]

    def queryset(self, request, queryset):
        if self.value() in {'1', '2', '3', '4', '5'}:
            return queryset.filter(score=self.value())
        return queryset


class CommentDateFilter(admin.DateFieldListFilter):
    template = 'admin/community_filter.html'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = 'Ngày gửi'
