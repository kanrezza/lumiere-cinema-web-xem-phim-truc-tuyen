"""Video issue reports and their resolution state."""
from django.contrib import admin

from .common import LocalizedAdminMixin, preview_text


class ReportAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Báo lỗi'
    model_label_plural = 'Báo lỗi video'
    list_display = ('report_text', 'episode_name', 'reporter', 'is_resolved', 'created_time')
    list_select_related = ('user', 'episode__movie')
    list_filter = ('resolved',)
    search_fields = ('description', 'episode__movie__title', 'user__username')
    readonly_fields = ('created_time',)
    fields = ('user', 'episode', 'description', 'resolved', 'created_time')
    field_labels = {'user': 'Người báo lỗi', 'episode': 'Tập phim', 'description': 'Mô tả vấn đề', 'resolved': 'Đã xử lý'}

    @admin.display(description='Nội dung báo lỗi')
    def report_text(self, obj): return preview_text(obj.description)

    @admin.display(description='Tập phim', ordering='episode__movie__title')
    def episode_name(self, obj): return str(obj.episode)

    @admin.display(description='Người gửi', ordering='user__username')
    def reporter(self, obj): return obj.user.username

    @admin.display(description='Đã xử lý', boolean=True, ordering='resolved')
    def is_resolved(self, obj): return obj.resolved

    @admin.display(description='Ngày gửi', ordering='created_at')
    def created_time(self, obj): return obj.created_at
