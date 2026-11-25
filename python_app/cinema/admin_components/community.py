"""Comment moderation, rating summaries and room supervision."""
from urllib.parse import urlencode

from django.contrib import admin
from django.contrib.admin.models import CHANGE, LogEntry
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from ..models import Comment, Room
from ..rooms.media import reset_room_media
from .common import LocalizedAdminMixin, preview_text
from .filters import (
    CommentDateFilter, CommunityMovieFilter, CommunityRatingFilter,
    CommunityRoomMovieFilter, ModerationReasonFilter,
)


class CommunityAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    show_facets = admin.ShowFacets.NEVER

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        # Django can return a redirect or an action confirmation for this route.
        context = getattr(response, 'context_data', None)
        if context is None or 'cl' not in context:
            return response
        cl = context['cl']
        movie_filter = next((spec for spec in cl.filter_specs if isinstance(spec, CommunityMovieFilter)), None)
        movie_id = movie_filter.value() if movie_filter else None
        selected_movie = next((title for pk, title in movie_filter.lookup_choices if str(pk) == movie_id), None) if movie_id else None
        context['community'] = {
            'description': self.community_description,
            'empty_detail': self.community_empty_detail,
            'selected_movie': selected_movie,
            'summary': self.community_summary(request, cl),
        }
        return response

    def community_summary(self, request, cl):
        return []

    def movie_filter_link(self, movie):
        url = reverse(f'admin:cinema_{self.model._meta.model_name}_changelist')
        return format_html('<a class="studio-community-movie-link" href="{}?{}">{}</a>',
                           url, urlencode({'movie': movie.pk}), movie.title)


class CommentAdmin(CommunityAdmin):
    model_label = 'Bình luận'
    model_label_plural = 'Bình luận'
    list_display = ('short_content', 'movie_name', 'author', 'moderation_status_display', 'moderation_reason_display', 'created_time')
    list_select_related = ('user', 'movie')
    list_filter = (CommunityMovieFilter, ModerationReasonFilter, 'moderation_status', ('created_at', CommentDateFilter))
    search_fields = ('content', 'movie__title', 'user__username')
    community_description = 'Đọc bình luận theo phim, xem lý do gắn cờ và duyệt nội dung.'
    community_search_placeholder = 'Tìm nội dung, tên phim hoặc tài khoản…'
    community_empty_detail = 'Bình luận mới sẽ xuất hiện tại đây. Nội dung được gắn cờ sẽ vào mục Chờ duyệt.'
    ordering = ('-created_at', '-pk')
    actions = ('approve_comments', 'hide_comments')
    readonly_fields = ('created_time', 'moderation_evidence')
    fields = ('user', 'movie', 'content', 'created_time', 'moderation_status', 'moderation_evidence')
    field_labels = {
        'user': 'Người dùng', 'movie': 'Phim', 'content': 'Nội dung bình luận',
        'moderation_status': 'Trạng thái duyệt',
    }
    field_help = {'moderation_status': 'Chọn Đang hiển thị để duyệt, hoặc Đã ẩn để gỡ khỏi trang phim.'}

    def get_fields(self, request, obj=None):
        if obj is None:
            return ('user', 'movie', 'content')
        return super().get_fields(request, obj)

    def community_summary(self, request, cl):
        parameter = 'moderation_status__exact'
        active_status_filter = next((spec for spec in cl.filter_specs if parameter in spec.expected_parameters()), None)
        counts_queryset = cl.get_queryset(request, exclude_parameters=active_status_filter.expected_parameters()) if active_status_filter else cl.queryset
        counts = counts_queryset.aggregate(
            total=Count('pk'),
            **{status.value: Count('pk', filter=Q(moderation_status=status)) for status in Comment.Status},
        )
        current_status = cl.params.get(parameter, '')
        cards = [('', 'Tất cả bình luận', counts['total'])]
        for status in (Comment.Status.PENDING, Comment.Status.PUBLISHED, Comment.Status.HIDDEN):
            cards.append((status.value, status.label, counts[status.value]))
        summary = []
        for status, label, value in cards:
            url = cl.get_query_string({parameter: status or None}, remove=['p'])
            summary.append({'label': label, 'value': value, 'url': url, 'active': current_status == status})
        return summary

    @admin.display(description='Bình luận')
    def short_content(self, obj): return preview_text(obj.content)

    @admin.display(description='Phim', ordering='movie__title')
    def movie_name(self, obj): return self.movie_filter_link(obj.movie)

    @admin.display(description='Người dùng', ordering='user__username')
    def author(self, obj): return obj.user.username

    @admin.display(description='Ngày gửi', ordering='created_at')
    def created_time(self, obj): return obj.created_at

    @admin.display(description='Trạng thái duyệt', ordering='moderation_status')
    def moderation_status_display(self, obj):
        return format_html('<span class="studio-community-badge" data-status="{}">{}</span>',
                           obj.moderation_status, obj.get_moderation_status_display())

    @admin.display(description='Lý do gắn cờ')
    def moderation_reason_display(self, obj):
        reasons = [(reason, label) for reason, label in Comment.Reason.choices if reason in obj.moderation_matches]
        if reasons:
            return format_html_join(' ', '<span class="studio-community-reason" data-reason="{}">{}</span>', reasons)
        return None

    @admin.display(description='Cụm từ được phát hiện')
    def moderation_evidence(self, obj):
        labels = dict(Comment.Reason.choices)
        return format_html_join(' ', '<div><strong>{}</strong><br>{}</div>',
                                ((labels[reason], ', '.join(phrases)) for reason, phrases in obj.moderation_matches.items()
                                 if reason in labels)) or 'Không có cụm từ được gắn cờ.'

    def save_model(self, request, obj, form, change):
        # The moderator's explicit edit of the status takes precedence over a new text match.
        reviewed_status = obj.moderation_status if change and 'moderation_status' in form.changed_data else None
        super().save_model(request, obj, form, change)
        if reviewed_status is not None and obj.moderation_status != reviewed_status:
            obj.moderation_status = reviewed_status
            obj.save(update_fields=['moderation_status'])

    def set_moderation_status(self, request, queryset, status, action_label):
        eligible = queryset.exclude(moderation_status=status)
        with transaction.atomic(using=queryset.db):
            entries = list(eligible.select_related(None).select_for_update().only('pk'))
            ids = [entry.pk for entry in entries]
            count = queryset.model.objects.using(queryset.db).filter(pk__in=ids).update(moderation_status=status)
            if count:
                LogEntry.objects.log_actions(request.user.pk, entries, CHANGE, action_label)
        self.message_user(request, f'{action_label} {count} bình luận.')

    @admin.action(permissions=['change'], description='Duyệt và hiển thị bình luận đã chọn')
    def approve_comments(self, request, queryset):
        self.set_moderation_status(request, queryset, Comment.Status.PUBLISHED, 'Đã duyệt')

    @admin.action(permissions=['change'], description='Ẩn bình luận đã chọn')
    def hide_comments(self, request, queryset):
        self.set_moderation_status(request, queryset, Comment.Status.HIDDEN, 'Đã ẩn')


class RatingAdmin(CommunityAdmin):
    model_label = 'Đánh giá'
    model_label_plural = 'Đánh giá'
    list_display = ('movie_name', 'author', 'rating_score', 'updated_time')
    list_display_links = ('rating_score',)
    list_select_related = ('user', 'movie')
    list_filter = (CommunityMovieFilter, CommunityRatingFilter)
    search_fields = ('movie__title', 'user__username')
    community_description = 'Xem phim được chấm, người đánh giá và điểm từ 1 đến 5.'
    community_search_placeholder = 'Tìm tên phim hoặc tài khoản…'
    community_empty_detail = 'Khi người xem chấm sao trên trang phim, điểm và tên phim sẽ xuất hiện tại đây.'
    ordering = ('-updated_at', '-pk')
    readonly_fields = ('updated_time',)
    field_labels = {'user': 'Người dùng', 'movie': 'Phim', 'score': 'Điểm đánh giá (1–5)'}

    def community_summary(self, request, cl):
        totals = cl.queryset.aggregate(ratings=Count('pk'), movies=Count('movie', distinct=True), average=Avg('score'))
        average = totals['average']
        return [
            {'label': 'Lượt đánh giá', 'value': totals['ratings']},
            {'label': 'Phim được đánh giá', 'value': totals['movies']},
            {'label': 'Điểm trung bình / 5', 'value': f'{average:.1f}'.replace('.', ',') if average is not None else '—'},
        ]

    @admin.display(description='Phim', ordering='movie__title')
    def movie_name(self, obj): return self.movie_filter_link(obj.movie)

    @admin.display(description='Người dùng', ordering='user__username')
    def author(self, obj): return obj.user.username

    @admin.display(description='Điểm / 5', ordering='score')
    def rating_score(self, obj):
        return format_html('<span class="studio-community-score">{} / 5</span>', obj.score)

    @admin.display(description='Cập nhật', ordering='updated_at')
    def updated_time(self, obj): return obj.updated_at


class RoomAdmin(CommunityAdmin):
    model_label = 'Phòng xem'
    model_label_plural = 'Phòng xem chung'
    list_display = ('room_name', 'host_name', 'movie_name', 'episode_name', 'is_closed', 'is_playing', 'created_time')
    list_select_related = ('host', 'episode__movie')
    list_filter = (CommunityRoomMovieFilter, 'closed', 'playing')
    search_fields = ('name', 'host__username', 'episode__movie__title', 'episode__title')
    community_description = 'Theo dõi phòng theo phim, tập đang chiếu và chủ phòng.'
    community_search_placeholder = 'Tìm tên phòng, phim, tập hoặc chủ phòng…'
    community_empty_detail = 'Phòng xem chung sẽ xuất hiện tại đây khi người xem tạo phòng.'
    ordering = ('-created_at', '-pk')
    readonly_fields = ('created_time',)
    fields = ('name', 'host', 'episode', 'closed', 'playing', 'position', 'created_time')
    field_labels = {'name': 'Tên phòng', 'host': 'Chủ phòng', 'episode': 'Tập phim', 'closed': 'Đã đóng phòng', 'playing': 'Đang phát', 'position': 'Vị trí phát (giây)'}

    def save_model(self, request, obj, form, change):
        if change:
            current = Room.objects.select_for_update().get(pk=obj.pk)
            obj.media_version = current.media_version
            if obj.episode_id != current.episode_id:
                reset_room_media(obj, obj.episode)
        super().save_model(request, obj, form, change)

    @admin.display(description='Phòng xem', ordering='name')
    def room_name(self, obj): return obj.name

    @admin.display(description='Chủ phòng', ordering='host__username')
    def host_name(self, obj): return obj.host.username

    @admin.display(description='Phim', ordering='episode__movie__title')
    def movie_name(self, obj): return self.movie_filter_link(obj.episode.movie) if obj.episode_id else 'Chưa chọn phim'

    @admin.display(description='Tập đang chiếu', ordering='episode__number')
    def episode_name(self, obj): return f'Tập {obj.episode.number} · {obj.episode.title}' if obj.episode_id else 'Phòng chờ'

    @admin.display(description='Đã đóng', boolean=True, ordering='closed')
    def is_closed(self, obj): return obj.closed

    @admin.display(description='Đang phát', boolean=True, ordering='playing')
    def is_playing(self, obj): return obj.playing

    @admin.display(description='Ngày tạo', ordering='created_at')
    def created_time(self, obj): return obj.created_at
