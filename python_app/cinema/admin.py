from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('Lumière', {'fields': ('bio', 'vip_until')}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('Liên hệ', {'fields': ('email',)}),)

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ('title', 'year', 'is_vip', 'published')
    list_filter = ('is_vip', 'published', 'kind')
    search_fields = ('title',)
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ('categories', 'actors')

@admin.register(Episode)
class EpisodeAdmin(admin.ModelAdmin):
    list_display = ('movie', 'number', 'status', 'duration')
    readonly_fields = ('asset_id', 'status', 'duration', 'error')
    def save_model(self, request, obj, form, change):
        if 'source' in form.changed_data:
            obj.status = 'pending'
            obj.error = ''
        super().save_model(request, obj, form, change)
    # Original file URLs are never rendered; replacement requires a new episode.
    def get_exclude(self, request, obj=None): return ('source',) if obj and obj.source else ()

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'amount', 'status', 'created_at')
    readonly_fields = tuple(f.name for f in Order._meta.fields)
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False

admin.site.register([Category, Actor, Comment, Rating, Report, Plan, Room])
admin.site.site_header = 'Lumière • Quản trị'
admin.site.site_title = 'Lumière Studio'
