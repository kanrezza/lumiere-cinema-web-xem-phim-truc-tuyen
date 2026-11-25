"""Subtitle upload validation and editing."""
from django import forms
from django.contrib import admin

from ..models import Subtitle
from ..subtitles import normalize_subtitle
from .common import LocalizedAdminMixin, UploadValidationAdminMixin


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


class SubtitleAdmin(UploadValidationAdminMixin, LocalizedAdminMixin, admin.ModelAdmin):
    upload_error_attribute = '_subtitle_upload_error'
    model_label = 'Phụ đề'
    model_label_plural = 'Phụ đề'
    form = SubtitleAdminForm
    list_display = ('episode', 'language', 'label')
    list_select_related = ('episode__movie',)
    list_filter = ('language',)
    search_fields = ('episode__movie__title', 'label')
    autocomplete_fields = ('episode',)
