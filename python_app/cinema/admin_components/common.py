"""Shared presentation and form behavior for Lumière model admins."""
from django import forms
from django.contrib import admin
from django.db.models import BooleanField, Count


def named_field_filter(filter_base, title):
    """Localize a filter instance without mutating Django's shared filter classes."""
    class NamedFilter(filter_base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.title = title
    return NamedFilter


def preview_text(text, limit=100):
    return text[:limit] + ('…' if len(text) > limit else '')


def format_vnd(amount):
    return f'{amount:,}'.replace(',', '.') + ' ₫'


class LocalizedAdminMixin:
    """Present editor labels without changing model/database metadata."""
    model_label = ''
    model_label_plural = ''
    field_labels = {}
    field_help = {}
    list_per_page = 25
    empty_value_display = '—'

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # Supply metadata while Django constructs fields. Editing base_fields
        # later is lost when upload-validation forms subclass the ModelForm.
        if db_field.name in self.field_labels:
            kwargs['label'] = self.field_labels[db_field.name]
        if db_field.name in self.field_help:
            kwargs['help_text'] = self.field_help[db_field.name]
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_list_filter(self, request):
        filters = []
        for entry in super().get_list_filter(request):
            if not isinstance(entry, str) or entry not in self.field_labels:
                filters.append(entry)
                continue
            field = self.model._meta.get_field(entry)
            base = admin.BooleanFieldListFilter if isinstance(field, BooleanField) else (
                admin.ChoicesFieldListFilter if field.choices else admin.AllValuesFieldListFilter)
            label = self.field_labels[entry]
            filters.append((entry, named_field_filter(base, label)))
        return filters

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            callback, name, _ = actions['delete_selected']
            actions['delete_selected'] = (callback, name, 'Xóa các bản ghi đã chọn')
        return actions

    def changelist_view(self, request, extra_context=None):
        context = {'title': self.model_label_plural or self.model_label}
        context.update(extra_context or {})
        return super().changelist_view(request, extra_context=context)

    def add_view(self, request, form_url='', extra_context=None):
        context = {'title': f'Thêm {self.model_label.lower()}'}
        context.update(extra_context or {})
        return super().add_view(request, form_url=form_url, extra_context=context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        context = {'title': f'Chỉnh sửa {self.model_label.lower()}'}
        context.update(extra_context or {})
        return super().change_view(request, object_id, form_url=form_url, extra_context=context)


class UploadValidationAdminMixin:
    """Expose upload-handler errors through the model form's normal validation."""
    upload_error_attribute = ''

    def get_form(self, request, obj=None, **kwargs):
        base = super().get_form(request, obj, **kwargs)
        error_attribute = self.upload_error_attribute

        class UploadCheckedForm(base):
            def clean(self):
                cleaned = super().clean()
                error = getattr(request, error_attribute, None)
                if error:
                    raise forms.ValidationError(error)
                return cleaned

        return UploadCheckedForm


class MovieCountAdminMixin:
    """Use one annotated query for film counts on related catalog directories."""
    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_movie_count=Count('movie', distinct=True))

    @admin.display(description='Số phim', ordering='_movie_count')
    def movie_count(self, obj):
        return obj._movie_count
