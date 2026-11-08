from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django import forms
from .models import *
from .subtitles import normalize_subtitle

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('Lumière', {'fields': ('bio', 'vip_until')}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('Liên hệ', {'fields': ('email',)}),)

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ('title', 'year', 'imdb_rating', 'is_cinema_release', 'is_vip', 'published')
    list_filter = ('is_vip', 'is_cinema_release', 'published', 'kind')
    search_fields = ('title', 'imdb_id')
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ('categories', 'actors')

    def get_form(self, request, obj=None, **kwargs):
        base = super().get_form(request, obj, **kwargs)
        class UploadCheckedForm(base):
            def clean(self):
                cleaned = super().clean()
                if getattr(request, '_trailer_upload_error', None):
                    raise forms.ValidationError(request._trailer_upload_error)
                return cleaned
        return UploadCheckedForm

@admin.register(Episode)
class EpisodeAdmin(admin.ModelAdmin):
    list_display = ('movie', 'number', 'status', 'duration')
    search_fields = ('movie__title', 'title')
    readonly_fields = ('asset_id', 'status', 'duration', 'error')
    def save_model(self, request, obj, form, change):
        if 'source' in form.changed_data:
            obj.status = 'pending'
            obj.error = ''
        super().save_model(request, obj, form, change)
    # Original file URLs are never rendered; replacement requires a new episode.
    def get_exclude(self, request, obj=None): return ('source',) if obj and obj.source else ()

class SubtitleAdminForm(forms.ModelForm):
    upload_file = forms.FileField(
        label='File phụ đề', required=False,
        help_text='SRT hoặc WebVTT UTF-8, tối đa 2 MB. Thêm mới cần file; khi sửa có thể giữ nguyên file hiện tại.',
    )

    class Meta:
        model = Subtitle
        fields = ('episode', 'language', 'label')

    def clean(self):
        cleaned = super().clean()
        upload = cleaned.get('upload_file')
        if upload:
            try:
                self.instance.content = normalize_subtitle(upload)
            except forms.ValidationError as error:
                self.add_error('upload_file', error)
        elif not self.instance.pk or not self.instance.content:
            self.add_error('upload_file', 'Chọn file SRT hoặc VTT cho phụ đề mới.')
        return cleaned


@admin.register(Subtitle)
class SubtitleAdmin(admin.ModelAdmin):
    form = SubtitleAdminForm
    list_display = ('episode', 'language', 'label')
    list_filter = ('language',)
    search_fields = ('episode__movie__title', 'label')
    autocomplete_fields = ('episode',)

    def get_form(self, request, obj=None, **kwargs):
        base = super().get_form(request, obj, **kwargs)

        class UploadCheckedForm(base):
            def clean(self):
                cleaned = super().clean()
                if getattr(request, '_subtitle_upload_error', None):
                    raise forms.ValidationError(request._subtitle_upload_error)
                return cleaned

        return UploadCheckedForm

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'amount', 'status', 'created_at')
    readonly_fields = tuple(f.name for f in Order._meta.fields)
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False

admin.site.register([Category, Actor, Comment, Rating, Report, Plan, Room])
admin.site.site_header = 'Lumière • Quản trị'
admin.site.site_title = 'Lumière Studio'
