"""Only editorial staff explicitly entrusted with broadcasting can operate premieres."""

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils import timezone

from ..models import Episode, Premiere
from ..premieres import can_manage_premieres, premiere_phase
from .common import LocalizedAdminMixin


class PremiereForm(forms.ModelForm):
    class Meta:
        model = Premiere
        fields = ['title', 'episode', 'audience', 'scheduled_at']

    def clean(self):
        data = super().clean()
        scheduled = data.get('scheduled_at')
        if not self.instance.pk or self.instance._state.adding:
            if scheduled and scheduled <= timezone.now():
                self.add_error('scheduled_at', 'Chọn thời gian trong tương lai. Bạn có thể bấm bắt đầu ngay sau khi lưu.')
        elif self.changed_data:
            current = Premiere.objects.select_related('episode__movie').filter(pk=self.instance.pk).first()
            if current and premiere_phase(current) != Premiere.Status.SCHEDULED:
                raise ValidationError('Suất chiếu đã bắt đầu hoặc kết thúc. Hãy tạo một suất chiếu mới.')
            if scheduled and scheduled <= timezone.now():
                self.add_error('scheduled_at', 'Giờ công chiếu mới phải ở tương lai.')
        return data


class PremiereAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    form = PremiereForm
    model_label = 'Suất công chiếu'
    model_label_plural = 'Công chiếu'
    list_display = ['title', 'episode', 'audience', 'scheduled_at', 'current_phase']
    list_filter = ['audience']
    search_fields = ['title', 'episode__title', 'episode__movie__title']
    list_select_related = ['episode__movie']
    fields = ['title', 'episode', 'audience', 'scheduled_at', 'screening_link', 'current_phase']
    readonly_fields = ['screening_link', 'current_phase']
    actions = None

    def has_module_permission(self, request):
        return can_manage_premieres(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_premieres(request.user)

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission

    def has_delete_permission(self, request, obj=None):
        return False

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'episode':
            kwargs['queryset'] = Episode.objects.filter(movie__published=True, status='ready', duration__gte=Premiere.MIN_DURATION).select_related('movie')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description='Trạng thái hiện tại')
    def current_phase(self, obj):
        if not obj or obj._state.adding:
            return 'Chưa lên lịch'
        return Premiere.Status(premiere_phase(obj)).label

    @admin.display(description='Phòng công chiếu')
    def screening_link(self, obj):
        if not obj or obj._state.adding:
            return 'Lưu lịch trước khi mở buổi công chiếu.'
        from django.urls import reverse
        from django.utils.html import format_html
        return format_html('<a href="{}">Mở trang công chiếu và điều khiển →</a>', reverse('premiere', args=[obj.pk]))

    def save_model(self, request, obj, form, change):
        # Admin change views already run in atomic(); lock the persisted state to
        # reject an editor that became stale while another tab began broadcasting.
        if change:
            current = Premiere.objects.select_for_update().select_related('episode__movie').get(pk=obj.pk)
            if premiere_phase(current) != Premiere.Status.SCHEDULED:
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied('Suất công chiếu đã bắt đầu; không thể đổi lịch hoặc nguồn phim.')
            obj.state_version = current.state_version + 1
        else:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class PremiereMessageAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Tin nhắn công chiếu'
    model_label_plural = 'Tin nhắn công chiếu'
    list_display = ['premiere', 'user', 'content', 'hidden', 'created_at']
    list_filter = ['hidden', 'premiere']
    search_fields = ['content', 'user__username', 'premiere__title']
    list_select_related = ['premiere', 'user']
    readonly_fields = ['premiere', 'user', 'content', 'moderation_matches', 'created_at']
    fields = ['premiere', 'user', 'content', 'hidden', 'moderation_matches', 'created_at']

    def has_module_permission(self, request):
        return can_manage_premieres(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_premieres(request.user)

    has_change_permission = has_view_permission

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
